from pathlib import Path
import json
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.logging_utils import log_event
from core.verify import file_exists
from domains.desktop.agentos_actuators import AgentOSActuators
from domains.desktop.rules_agentos import generate_agentos_AF

LOG_PATH = Path("runs/isl_nano_run_desktop_agentos.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_cfg():
    return json.loads(Path("configs/agentos.json").read_text())

def main(goals=("ide_hello","web_search")):
    cfg = load_cfg()
    acts = AgentOSActuators(cfg["project_root"], cfg.get("python_exe"))
    artifacts = cfg["artifacts"]

    with LOG_PATH.open("w") as fp:
        log_event(fp, "sense", {"agentos_root": cfg["project_root"], "goals": list(goals)})
        af = generate_agentos_AF(list(goals), artifacts)
        log_event(fp, "arguments", {"ids": list(af.args.keys()), "attacks": list(map(list, af.attacks))})
        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        steps = order_plan(af.args, af.args.keys())
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})

        # precondition facts (from filesystem for reruns)
        facts = set()
        if Path(cfg["project_root"], artifacts["hello_stdout"]).exists():
            facts.add("fs:hello_stdout exists")
        if Path(cfg["project_root"], artifacts["search_png"]).exists():
            facts.add("fs:search_png exists")

        def pre_ok(pre): return all(p in facts for p in pre)
        def update_facts(a):
            if a.id == "A_run_ide_hello": facts.add("fs:hello_stdout exists")
            if a.id == "A_run_web_search": facts.add("fs:search_png exists")

        queue = list(steps)
        max_iters = len(queue)*4
        iters = 0
        while queue and iters < max_iters:
            iters += 1
            step = queue.pop(0)
            a = af.args[step.arg_id]

            if not pre_ok(a.pre):
                queue.append(step)
                continue

            if a.action.name == "run_goal":
                res = acts.run_goal(a.action.params["goal"])
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params, "proc": res})
                if res["returncode"] != 0:
                    log_event(fp, "verify", {"check":"proc_exitcode_ok","status":"FAIL","returncode":res["returncode"]})
                    print("❌ AgentOS goal failed"); return
                update_facts(a)
            elif a.verify.name == "file_exists":
                v = a.verify.params
                path = str(Path(cfg["project_root"], v["path"]))
                res = file_exists(path, timeout_s=float(v["timeout_s"]))
                log_event(fp, "verify", res)
                if res["status"] != "PASS":
                    print("❌ Artifact not found", path); return
            elif a.action.name == "noop":
                log_event(fp, "actuate", {"arg": a.id, "action": "noop"})
            else:
                raise ValueError(f"Unknown action: {a.action.name}")

        if queue:
            print("❌ Could not schedule all steps — unmet preconditions remain."); return
        print("✅ Desktop (AgentOS) tasks complete. Log:", LOG_PATH)

if __name__ == "__main__":
    main()
