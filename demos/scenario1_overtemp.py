from pathlib import Path
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.verify import in_band
from core.logging_utils import log_event, span, log_metrics
from domains.plant.model import make_plant, Sensors, Actuators
# from domains.plant.sensors import PlantSensors
# from domains.plant.actuators import PlantActuators
from domains.plant.rules import generate_overtemp_AF
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()
from core.ablation import is_no_af, is_no_diag, is_no_priority, get_ablation
import os

# ...
LOG_PATH = Path(os.environ.get("ISL_LOG_PATH", "runs/isl_nano_run_overtemp.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    # Perfect-condition initial state
    plant = make_plant(temp=90.0, T_env=25.0)  # over temperature start
    sens = Sensors(plant)
    acts = Actuators(plant)

    # Thresholds / goal band
    T_HIGH = 80.0
    TARGET = 70.0
    TOL = 0.5
    TIMEOUT = 30.0
    DT = 0.1  # simulation step (s)

    with LOG_PATH.open("w") as fp:
        ablation = get_ablation()
        log_event(fp, "config", {"ablation": ablation})
        emit_info(f"Ablation mode: {ablation}")
        
        # Sense → Arguments
        with span(fp, "sense"):
            temp = sens.read_temp()
            log_event(fp, "sense", {"temp": temp})

        with span(fp, "reason", {"iter": 0}):
            # generate AF (unchanged)
            af = generate_overtemp_AF(temp, T_HIGH=T_HIGH, target=TARGET, tol=TOL, timeout_s=TIMEOUT)
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


        # Solve grounded
        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        if not ext:
            print("No admissible actions; nothing to do.")
            return

        # Order plan
        steps = order_plan(af.args, ext)
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})

        steps_executed = 0
        first_fail_t = None
        af_iters = 1  # this scenario typically has 1 iteration

        # Execute (only one step expected)
        for step in steps:
            a = af.args[step.arg_id]
            with span(fp, "act", {"arg": a.id}):
                if a.action.name == "open_valve":
                    acts.open_valve(a.action.params.get("valve","V_cool"), float(a.action.params.get("u",0.7)))
                elif a.action.name == "set_heater_power":
                    acts.set_heater_power(float(a.action.params.get("p",0.0)))
                elif a.action.name == "noop":
                    acts.noop()
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})
                steps_executed += 1

            with span(fp, "verify", {"arg": a.id}):
                res = in_band(get_metric=sens.read_temp, target=TARGET, tol=TOL, timeout_s=TIMEOUT, step_fn=plant.step, dt=DT)
            log_event(fp, "verify", res)

            if res.get("status") == "PASS":
                emit_ok("Alarm cleared: temperature reached the safe target.")
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
