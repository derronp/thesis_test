from pathlib import Path
import json
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.arguments import ArgFramework
from core.logging_utils import log_event
from core.verify import file_exists, proc_exitcode_ok
from domains.desktop.agentos_actuators import AgentOSActuators
from llm.adapter import LLMAdapter
from llm.providers.lmstudio import LMStudioProvider
from llm.providers.mock_desktop import MockDesktopProvider

LOG_PATH = Path("runs/isl_nano_run_desktop_agentos_llm.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_cfg():
    return json.loads(Path("configs/agentos.json").read_text())

def load_llm_cfg():
    p = Path("configs/llm.json")
    if not p.exists():
        return {"provider":"lmstudio","model":"qwen/qwen3-4b-2507","base_url":"http://127.0.0.1:1234/v1","api_key":"lm-studio"}
    return json.loads(p.read_text())

def make_provider(llm_cfg):
    prov = llm_cfg.get("provider", "lmstudio")
    if prov == "lmstudio":
        return LMStudioProvider(model=llm_cfg.get("model","qwen/qwen3-4b-2507"),
                                base_url=llm_cfg.get("base_url","http://127.0.0.1:1234/v1"),
                                api_key=llm_cfg.get("api_key","lm-studio"))
    return MockDesktopProvider()

def main(goals=("ide_hello","web_search")):
    cfg = load_cfg(); llm_cfg = load_llm_cfg()
    provider = make_provider(llm_cfg)

    acts = AgentOSActuators(cfg["project_root"], cfg.get("python_exe"))
    artifacts = cfg["artifacts"]
    ctx = {"goals": goals, "artifacts": artifacts}

    adapter = LLMAdapter(provider)
    llm_args = adapter.generate_arguments(ctx)
    args = {a.id: a for a in llm_args}
    # Prefer run before verify
    attacks = set([("L_verify_ide_hello","L_run_ide_hello"), ("L_verify_web_search","L_run_web_search")])
    af = ArgFramework(args=args, attacks=attacks)

    with LOG_PATH.open("w") as fp:
        log_event(fp, "sense", {"agentos_root": cfg["project_root"], "goals": list(goals)})
        log_event(fp, "llm_cfg", {k: llm_cfg[k] for k in ("provider","model") if k in llm_cfg})
        log_event(fp, "arguments_llm", {"ids": list(args.keys())})
        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        steps = order_plan(af.args, af.args.keys())
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})

        facts = set()
        if Path(cfg["project_root"], artifacts["hello_stdout"]).exists():
            facts.add("fs:hello_stdout exists")
        if Path(cfg["project_root"], artifacts["search_png"]).exists():
            facts.add("fs:search_png exists")

        def pre_ok(pre): return all(p in facts for p in pre)
        def update_facts(aid):
            if aid.endswith("ide_hello"): facts.add("fs:hello_stdout exists")
            if aid.endswith("web_search"): facts.add("fs:search_png exists")

        queue = list(steps); max_iters = len(queue)*4; iters=0
        while queue and iters < max_iters:
            iters += 1
            step = queue.pop(0); a = af.args[step.arg_id]
            if not pre_ok(a.pre):
                queue.append(step); continue

            if a.action.name == "run_goal":
                goal = a.action.params["goal"]
                res = acts.run_goal(goal)
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params, "proc": res})
                if res["returncode"] != 0:
                    log_event(fp, "verify", {"check":"proc_exitcode_ok","status":"FAIL","returncode":res["returncode"],"stderr":res.get("stderr","")})
                    print("❌ AgentOS goal failed:", goal); return
                update_facts(a.id)

            elif a.action.name == "noop" and a.verify.name == "file_exists":
                v = a.verify.params
                path = str(Path(cfg["project_root"], v["path"]))
                res = file_exists(path, timeout_s=float(v["timeout_s"]))
                log_event(fp, "verify", res)
                if res["status"] != "PASS": print("❌ Artifact not found:", path); return

            else:
                if a.verify.name == "proc_exitcode_ok":
                    res = proc_exitcode_ok(a.verify.params["cmd"], cwd=cfg["project_root"])
                    log_event(fp, "verify", res)
                    if res["status"] != "PASS": print("❌ Process check failed"); return
                else:
                    log_event(fp, "actuate", {"arg": a.id, "action": a.action.name})
                    log_event(fp, "verify", {"check": a.verify.name, "status": "SKIPPED"})

        if queue:
            print("❌ Could not schedule all steps — unmet preconditions remain."); return
        print("✅ Desktop (AgentOS) via LM Studio proposed steps complete. Log:", LOG_PATH)

if __name__ == "__main__":
    main()
