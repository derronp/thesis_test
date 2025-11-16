from pathlib import Path
import json, hashlib, sys
from core.af_solver import grounded_extension
from core.planner import order_plan
from core.logging_utils import log_event
from core.verify import file_exists, file_hash_equal, proc_exitcode_ok
from domains.desktop.actuators import DesktopActuators
from domains.desktop.sensors import DesktopSensors
from domains.desktop.rules_scraper import generate_scraper_AF
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()

LOG_PATH = Path("runs/isl_nano_run_desktop_scraper.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
WORKSPACE = "workspace_s3"

SCRAPER_PY = """import json, pathlib
from bs4 import BeautifulSoup
def main():
    root = pathlib.Path(__file__).parent
    html = (root / "sample.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    data = {"title": soup.title.string, "h1": soup.find("h1").get_text(strip=True)}
    (root/"output.json").write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
if __name__ == "__main__": main()
"""
TEST_PY = """from pathlib import Path
import json, subprocess, sys
def test_scraper_runs_and_outputs_expected():
    proc = subprocess.run([sys.executable, 'scraper.py'], cwd=str(Path(__file__).parent), capture_output=True, text=True)
    assert proc.returncode == 0
    out = json.loads((Path(__file__).parent/'output.json').read_text(encoding='utf-8'))
    assert out.get('title') == 'Demo Page'
    assert out.get('h1') == 'Hello ISL-NANO'
"""
def sha256_text(s: str) -> str:
    h = hashlib.sha256(); h.update(s.encode('utf-8')); return h.hexdigest()
def sha256_json(obj) -> str:
    h = hashlib.sha256(); 
    import json as _j; h.update(_j.dumps(obj, sort_keys=True).encode('utf-8')); return h.hexdigest()

def main():
    acts = DesktopActuators(WORKSPACE)
    sens = DesktopSensors(WORKSPACE)
    expected = {
        "scraper_sha": sha256_text(SCRAPER_PY),
        "test_sha": sha256_text(TEST_PY),
        "out_sha": sha256_json({"title":"Demo Page","h1":"Hello ISL-NANO"}),
    }
    with LOG_PATH.open("w") as fp:
        log_event(fp, "sense", {"workspace": WORKSPACE})
        af = generate_scraper_AF(state={}, expected=expected)
        log_event(fp, "arguments", {"ids": list(af.args.keys()), "attacks": list(map(list, af.attacks))})
        ext = grounded_extension(af)
        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        # Use all args so preconditions can pull in the necessary writes/tests deterministically
        steps = order_plan(af.args, af.args.keys())
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})

        # --- Helper: precondition check ---
        def pre_ok(pre: tuple, facts: set) -> bool:
            return all(p in facts for p in pre)
        # --- Helper: after a successful verify, update facts based on action/effects ---
        def update_facts_after_success(a, facts: set):
            # Infer facts from action/effects/verifier names
            if a.action.name == "write_file":
                kind = a.action.params.get("kind")
                if kind == "html":
                    facts.add("fs:sample.html exists")
                elif kind == "scraper":
                    facts.add("fs:scraper.py exists")
                elif kind == "tests":
                    facts.add("fs:test exists")
            elif a.action.name == "run_pytest":
                facts.add("tests:pass")
            elif a.action.name == "run_py":
                facts.add("out:output.json exists")
            # You can also optionally union any symbolic a.effects here:
            for e in a.effects:
                facts.add(e)

        # --- Build initial facts from the real filesystem (in case of reruns) ---
        facts = set()
        if (Path(WORKSPACE)/"project/sample.html").exists():
            facts.add("fs:sample.html exists")
        if (Path(WORKSPACE)/"project/scraper.py").exists():
            facts.add("fs:scraper.py exists")
        if (Path(WORKSPACE)/"project/test_scraper.py").exists():
            facts.add("fs:test exists")
        if (Path(WORKSPACE)/"project/output.json").exists():
            facts.add("out:output.json exists")

        # --- Execute respecting preconditions via a simple queue ---
        queue = list(steps)
        max_iters = len(queue) * 4  # safety to avoid infinite loops
        iters = 0
        while queue and iters < max_iters:
            iters += 1
            step = queue.pop(0)
            a = af.args[step.arg_id]

            if not pre_ok(a.pre, facts):
                # prerequisites not met yet → push to the back
                queue.append(step)
                continue
            # Execute this step now that preconditions are satisfied
            if a.action.name == "write_file":
                kind = a.action.params.get("kind")
                if kind == "html":
                    acts.create_sample_html("project/sample.html")
                elif kind == "scraper":
                    acts.write_file("project/scraper.py", SCRAPER_PY)
                elif kind == "tests":
                    acts.write_file("project/test_scraper.py", TEST_PY)
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})

                # Verify file write
                v = a.verify.params
                if a.verify.name == "file_exists":
                    res = file_exists(str(Path(WORKSPACE)/v["path"]), timeout_s=float(v["timeout_s"]))
                elif a.verify.name == "file_hash_equal":
                    res = file_hash_equal(str(Path(WORKSPACE)/v["path"]), v["expected_sha256"], timeout_s=float(v["timeout_s"]))
                else:
                    raise ValueError("Unknown verifier for write_file")

                log_event(fp, "verify", res)
                if res["status"] != "PASS":
                    emit_fail(f"Verification failed at. Log: {a.id}"); return
                update_facts_after_success(a, facts)

            elif a.action.name == "run_pytest":
                res = proc_exitcode_ok(a.verify.params["cmd"], cwd=str(Path(WORKSPACE)/a.verify.params["cwd"]), timeout_s=float(a.verify.params["timeout_s"]))
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params})
                log_event(fp, "verify", res)
                if res["status"] != "PASS":
                    emit_fail("Tests failed"); print(res.get("stdout",""), res.get("stderr","")); return
                update_facts_after_success(a, facts)

            elif a.action.name == "run_py":
                import sys
                res_run = proc_exitcode_ok([sys.executable, "scraper.py"], cwd=str(Path(WORKSPACE)/"project"))
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "params": a.action.params, "proc": res_run})
                if res_run["status"] != "PASS":
                    log_event(fp, "verify", res_run); emit_fail("run failed"); return
                # verify final output content
                res = file_hash_equal(str(Path(WORKSPACE)/"project/output.json"), expected["out_sha"], timeout_s=5.0)
                log_event(fp, "verify", res)
                if res["status"] != "PASS":
                    emit_fail("Output verification failed"); return
                update_facts_after_success(a, facts)

            else:
                raise ValueError(f"Unknown action: {a.action.name}")
        
        # all done?
        if queue:
            emit_fail("Could not schedule all steps – unmet preconditions remain.")
            return

        emit_ok("Desktop task complete: scraper built, tested, and output verified.")
        print(f"Log written to: {LOG_PATH}")


if __name__ == "__main__":
    main()
