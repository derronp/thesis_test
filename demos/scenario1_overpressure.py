from pathlib import Path
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.verify import in_band, reach_threshold
from core.logging_utils import log_event, span, log_metrics
from domains.plant.model import make_plant, Sensors, Actuators
# from domains.plant.sensors import PressureSensors
# from domains.plant.actuators import PressureActuators
from domains.plant.rules_overpressure import generate_overpressure_AF
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()
from core.ablation import is_no_af, is_no_diag, is_no_priority, get_ablation
import os

# ...
LOG_PATH = Path(os.environ.get("ISL_LOG_PATH", "runs/isl_nano_run_overpressure.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    # Perfect-condition initial state: high pressure
    plant = make_plant(pressure=2.5, p_env=1.0)  # choose your starting pressure/analog state
    sens = Sensors(plant)
    acts = Actuators(plant)

    # Thresholds / goal
    P_HIGH = 2.0
    TARGET = 1.2
    TIMEOUT = 30.0
    DT = 0.1

    with LOG_PATH.open("w") as fp:
        ablation = get_ablation()
        log_event(fp, "config", {"ablation": ablation})
        emit_info(f"Ablation mode: {ablation}")
        
        # Sense → Arguments
        with span(fp, "sense"):
            p = sens.read_pressure()
            log_event(fp, "sense", {"pressure": p})

        with span(fp, "reason", {"iter": 0}):
            # generate AF (unchanged)
            af = generate_overpressure_AF(p, P_HIGH=P_HIGH, target=TARGET, timeout_s=TIMEOUT)
            # (optional) priority filtering hook: if you have one, skip it when is_no_priority()
            attacks_raw = list(af.attacks)
            attacks_eff = attacks_raw  # default
            if is_no_priority():
                attacks_eff = attacks_raw  # no filter
            # (record the attacks used)
            log_event(fp, "arguments", {
                "ids": list(af.args.keys()),
                "attacks": list(map(list, attacks_eff)),
            })

            if is_no_af():
                ext = set(af.args.keys())  # bypass solver: admit all
            else:
                ext = grounded_extension(af)  # your normal call

            log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
            if not ext:
                emit_info("No admissible actions; nothing to do.")
                log_metrics(fp, status="FAIL", steps_to_success=0, af_iters=1)
                return

            steps = order_plan(af.args, ext)
            log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})


        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        if not ext:
            print("No admissible actions; nothing to do.")
            return

        steps_executed = 0
        first_fail_t = None
        af_iters = 1  # this scenario typically has 1 iteration

        # Execute (only one step expected)
        for step in steps:
            a = af.args[step.arg_id]
            with span(fp, "act", {"arg": a.id}):
                if a.action.name == "open_relief":
                    acts.open_relief(float(a.action.params.get("u",0.9)))
                elif a.action.name == "set_inflow":
                    acts.set_inflow(float(a.action.params.get("q",0.1)))
                elif a.action.name == "noop":
                    pass
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})
                steps_executed += 1

            with span(fp, "verify", {"arg": a.id}):
                if a.verify.name == "reach_threshold":
                    res = reach_threshold(
                        get_metric=sens.read_pressure,
                        target=float(a.verify.params["target"]),
                        direction=str(a.verify.params["direction"]),
                        timeout_s=float(a.verify.params["timeout_s"]),
                        step_fn=plant.step,
                        dt=DT,
                    )
                elif a.verify.name == "in_band":
                    res = in_band(
                        get_metric=sens.read_pressure,
                        target=float(a.verify.params["target"]),
                        tol=float(a.verify.params["tol"]),
                        timeout_s=float(a.verify.params["timeout_s"]),
                        step_fn=plant.step,
                        dt=DT,
                    )
                else:
                    raise ValueError(f"Unknown verifier: {a.verify.name}")
            log_event(fp, "verify", res)

            if res.get("status") == "PASS":
                emit_ok("Alarm cleared: pressure reached the safe target.")
                log_metrics(fp, status="PASS", steps_to_success=steps_executed, af_iters=af_iters,
                            time_to_fix_s=(0.0 if first_fail_t is None else (time.perf_counter()-first_fail_t)))
            else:
                emit_fail("Verification failed: did not reach target band in time.")
                if not is_no_diag():
                    # (If you had diagnosis for S1, place it here.)
                    pass
                log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
            break

if __name__ == "__main__":
    main()
