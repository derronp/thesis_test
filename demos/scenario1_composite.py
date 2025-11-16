from pathlib import Path
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.verify import in_band, reach_threshold
from core.logging_utils import log_event
from domains.plant.model import ThermalPlant, PressurePlant
from domains.plant.sensors import PlantSensors, PressureSensors
from domains.plant.actuators import PlantActuators, PressureActuators
from domains.plant.rules import generate_overtemp_AF
from domains.plant.rules_overpressure import generate_overpressure_AF
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()


LOG_DIR = Path("runs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

def run_overtemp(P_POLICY=True):
    log_path = LOG_DIR / "isl_nano_run_overtemp_composite.jsonl"
    plant = ThermalPlant(temp=90.0, T_env=25.0)
    sensors = PlantSensors(plant)
    acts = PlantActuators(plant)

    T_HIGH = 80.0
    TARGET = 70.0
    TOL = 0.5
    TIMEOUT = 60.0   # was 40.0
    DT = 0.02        # was 0.1 — finer step so we hit the band

    with log_path.open("w") as fp:
        temp = sensors.read_temp()
        log_event(fp, "sense", {"temp": temp})
        af = generate_overtemp_AF(temp, T_HIGH=T_HIGH, target=TARGET, tol=TOL, timeout_s=TIMEOUT)
        log_event(fp, "arguments", {"ids": list(af.args.keys()), "attacks": list(map(list, af.attacks))})

        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        if not ext:
            print("No admissible actions for overtemp.")
            return False, str(log_path)

        steps = order_plan(af.args, ext)
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
        a = af.args[steps[0].arg_id]

        # Execute: initial actuation
        if a.action.name == "open_valve":
            acts.open_valve(a.action.params.get("valve","V_cool"), float(a.action.params.get("u",0.7)))
        elif a.action.name == "set_heater_power":
            acts.set_heater_power(float(a.action.params.get("p",0.0)))

        log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})

        # P-like policy to smoothly reach band (with hysteresis)
        if P_POLICY:
            u_prev = 0.0
            def step_with_p(dt):
                nonlocal u_prev
                err = sensors.read_temp() - TARGET
                if err > TOL:
                    # stronger cooling when above band, base + proportional
                    u = min(1.0, 0.10 + 0.03 * err)
                elif err < -TOL:
                    # below band → stop cooling to avoid overshoot-down
                    u = 0.0
                else:
                    # inside band → gently decay valve to hold position
                    u = max(0.0, u_prev * 0.8)
                acts.open_valve("V_cool", u)
                u_prev = u
                plant.step(dt)
            step_fn = step_with_p
        else:
            step_fn = plant.step


        # Use in_band verifier for composite
        res = in_band(
            get_metric=sensors.read_temp,
            target=float(TARGET),
            tol=float(TOL),
            timeout_s=float(TIMEOUT),
            step_fn=step_fn,
            dt=DT,
        )
        log_event(fp, "verify", res)

        if res.get("status") == "PASS":
            emit_ok(
                f"Overtemp: temperature reached {'target band with P-policy' if P_POLICY else 'band'}."
            )
            return True, str(log_path)
        else:
            emit_fail("Overtemp: did not reach target band in time.")
            return False, str(log_path)

def run_overpressure(P_POLICY=True):
    log_path = LOG_DIR / "isl_nano_run_overpressure_composite.jsonl"
    plant = PressurePlant(pressure=2.5, p_env=1.0)
    sensors = PressureSensors(plant)
    acts = PressureActuators(plant)

    P_HIGH = 2.0
    TARGET = 1.2
    TOL = 0.05      # keep as 0.05
    TIMEOUT = 90.0  # was 60.0
    DT = 0.02       # keep fine step

    from domains.plant.rules_overpressure import generate_overpressure_AF
    with log_path.open("w") as fp:
        p = sensors.read_pressure()
        log_event(fp, "sense", {"pressure": p})
        af = generate_overpressure_AF(p, P_HIGH=P_HIGH, target=TARGET, timeout_s=TIMEOUT)
        log_event(fp, "arguments", {"ids": list(af.args.keys()), "attacks": list(map(list, af.attacks))})

        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        if not ext:
            print("No admissible actions for overpressure.")
            return False, str(log_path)

        steps = order_plan(af.args, ext)
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
        a = af.args[steps[0].arg_id]

        # Execute initial actuation
        if a.action.name == "open_relief":
            acts.open_relief(float(a.action.params.get("u",0.9)))
        elif a.action.name == "set_inflow":
            acts.set_inflow(float(a.action.params.get("q",0.1)))

        log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})

        # P-like policy for pressure to settle within band
        # P-like policy for pressure (two-phase with hysteresis)
        if P_POLICY:
            relief_prev, inflow_prev = 0.0, 0.5
            PHASE_SWITCH = 0.20   # when err > 0.20, use coarse (bang-bang-ish) phase
            DECAY = 0.85          # hold/decay factor inside band to avoid jitter

            def step_with_p(dt):
                nonlocal relief_prev, inflow_prev
                p = sensors.read_pressure()
                err = p - TARGET

                if err > TOL:
                    if err > PHASE_SWITCH:
                        # Phase A (coarse): get down quickly
                        relief = 1.0
                        inflow = 0.0
                    else:
                        # Phase B (fine): proportional toward band
                        # stronger proportional relief; reduce inflow near 0
                        relief = min(1.0, 0.10 + 2.0 * err)   # try 2.0–3.0 if needed
                        inflow = max(0.0, 0.10 - 0.50 * err)  # clamp to floor at 0
                elif err < -TOL:
                    # below band → stop venting; restore nominal inflow gently
                    relief = 0.0
                    inflow = 0.50
                else:
                    # inside band → gently decay toward last values to hold position
                    relief = max(0.0, relief_prev * DECAY)
                    # drift inflow toward a mild mid value to avoid slow drift
                    target_inflow = 0.40
                    inflow = max(0.0, min(1.0, DECAY * inflow_prev + (1.0 - DECAY) * target_inflow))

                acts.open_relief(relief)
                acts.set_inflow(inflow)
                relief_prev, inflow_prev = relief, inflow
                plant.step(dt)

            step_fn = step_with_p
        else:
            step_fn = plant.step

        res = in_band(
            get_metric=sensors.read_pressure,
            target=float(TARGET),
            tol=float(TOL),
            timeout_s=float(TIMEOUT),
            step_fn=step_fn,
            dt=DT,
        )
        log_event(fp, "verify", res)

        if res.get("status") == "PASS":
            emit_ok(
                f"Overpressure: pressure reached {'target band with P-policy' if P_POLICY else 'band'}."
            )
            return True, str(log_path)
        else:
            emit_fail("Overpressure: did not reach target band in time.")
            return False, str(log_path)

def main():
    # Choose initial conditions; composite picks which alarm to handle.
    # Toggle these two to test either branch deterministically.
    INIT_OVER_TEMP = True
    INIT_OVER_PRESSURE = False

    if INIT_OVER_TEMP:
        ok, log_path = run_overtemp(P_POLICY=True)
        return
    if INIT_OVER_PRESSURE:
        ok, log_path = run_overpressure(P_POLICY=True)
        return
    print("No alarm initial condition set. Set INIT_OVER_TEMP or INIT_OVER_PRESSURE.")

if __name__ == "__main__":
    main()
