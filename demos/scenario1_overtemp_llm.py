from pathlib import Path
from core.logging_utils import log_event
from core.af_solver import grounded_extension
from core.arguments import ArgFramework
from core.planner import order_plan
from core.verify import in_band
from domains.plant.model import PlantSim, Sensors, Actuators
from llm.adapter import LLMAdapter
from llm.providers.mock import MockProvider
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()


LOG_PATH = Path("runs/isl_nano_run_overtemp_llm.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

TARGET = 60.0; TOL = 0.5; DT = 0.02; TIMEOUT = 60.0

def main(P_POLICY=True):
    plant = PlantSim(); sensors = Sensors(plant); acts = Actuators(plant)
    ctx = {"temp0": sensors.read_temp(), "target": TARGET, "tol": TOL, "timeout_s": TIMEOUT}

    adapter = LLMAdapter(MockProvider())
    llm_args = adapter.generate_arguments(ctx)
    args = {a.id: a for a in llm_args}; attacks = set()
    af = ArgFramework(args=args, attacks=attacks)

    with LOG_PATH.open("w") as fp:
        log_event(fp, "sense", {"temp0": ctx["temp0"]})
        log_event(fp, "arguments_llm", {"ids": list(args.keys())})
        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        steps = order_plan(af.args, af.args.keys())
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})

        u_prev = 0.0
        def step_with_p(dt):
            nonlocal u_prev
            err = sensors.read_temp() - TARGET
            if err > TOL:
                u = min(1.0, 0.10 + 0.03 * err)
            elif err < -TOL:
                u = 0.0
            else:
                u = max(0.0, u_prev * 0.8)
            acts.open_valve("V_cool", u); u_prev = u; plant.step(dt)

        for s in steps:
            a = af.args[s.arg_id]
            if a.action.name == "noop":
                log_event(fp, "actuate", {"arg": a.id, "action": "noop"})
            elif a.action.name == "cool_to_target":
                log_event(fp, "actuate", {"arg": a.id, "action": "cool_to_target", "params": a.action.params})
                res = in_band(sensors.read_temp, TARGET, TOL, TIMEOUT, step_with_p if P_POLICY else plant.step, DT)
                log_event(fp, "verify", res)
                if res["status"] != "PASS":
                    emit_fail("LLM overtemp failed."); return False, str(LOG_PATH)
        emit_ok("LLM overtemp complete."); return True, str(LOG_PATH)

if __name__ == "__main__":
    main()
