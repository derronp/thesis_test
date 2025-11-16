from pathlib import Path
import json, time
from core.arguments import ArgFramework,ActionSpec, VerifySpec, Argument
from core.af_solver import grounded_extension,filter_attacks_by_priority
from core.planner import order_plan
from core.logging_utils import log_event, export_csv, summarize_sources
from core.logging_utils import span, log_metrics
from core.verify import (
    file_exists, file_hash_equal, proc_exitcode_ok,
    stdout_contains, stdout_regex, json_field_equals, dir_contains, file_glob_exists
)
from core.ablation import is_no_af, is_no_diag, is_no_priority, get_ablation
from domains.desktop.local_actuators import LocalDesktopActuators
from llm.adapter import LLMAdapter
from llm.provider_factory import make_provider
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()

import os

# ...
LOG_PATH = Path(os.environ.get("ISL_LOG_PATH", "runs/isl_nano_run_desktop_multistep_llm.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _make_diag_arg(failed_arg: Argument, reason: str) -> Argument:
    return Argument(
        id=f"D_{failed_arg.id}",
        domain=failed_arg.domain,
        topic="diagnosis",
        pre=tuple(),
        action=ActionSpec("noop", {}),
        effects=tuple(),
        verify=VerifySpec("noop", {}),
        priority=(getattr(failed_arg, "priority", 0) + 1),
        source="desktop_diag",
        role="diagnosis",
    )

def _verify_all(acts_root, v, fp):
    verifiers = []
    if isinstance(v, dict) and "verify_all" in v:
        verifiers = v["verify_all"]
    else:
        verifiers = [v]
    all_ok = True
    for one in verifiers:
        with span(fp, "verify", {"check": (one["name"] if isinstance(one, dict) else getattr(one,"name","?"))}):
            vr = _run_one_check(acts_root, one)
        log_event(fp, "verify", vr)
        if vr.get("status") != "PASS":
            all_ok = False
            break
    return all_ok

def _export_tables(args, ext, attacks_eff_current, suffix=""):
    try:
        from core.logging_utils import export_csv
    except Exception:
        import csv
        def export_csv(path, rows, header):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as fp:
                w = csv.writer(fp); w.writerow(header); [w.writerow(r) for r in rows]

    outdir = Path("runs"); outdir.mkdir(parents=True, exist_ok=True)
    if not suffix:
        iter_idx = globals().get("_af_iter", 0)
        suffix = f"_iter{iter_idx:02d}"
        globals()["_af_iter"] = iter_idx + 1

    acc = set(ext or [])
    rows = []
    for aid, a in args.items():
        rows.append([
            aid,
            "ACCEPTED" if aid in acc else "REJECTED",
            getattr(a, "priority", 0),
            getattr(a, "topic", ""),
            getattr(getattr(a, "action", None), "name", ""),
            getattr(a, "source", "unknown"),
            getattr(a, "role", ""),
        ])
    export_csv(outdir / f"af_selection{suffix}.csv", rows,
               header=["arg_id","status","priority","topic","action","source","role"])

    rows2 = []
    for edge in (attacks_eff_current or []):
        try: x,y = edge
        except Exception: continue
        rows2.append([x,y])
    export_csv(outdir / f"af_attacks{suffix}.csv", rows2, header=["attacker","target"])

    src_rows = summarize_sources(args, acc, attacks_eff_current)
    if src_rows:
        export_csv(outdir / f"af_sources{suffix}.csv", src_rows,
                   header=["source","role","total_args","accepted","rejected","acceptance_rate","attacks_out","attacks_in"])

def main(user_intent="Create a new dir 'proj', write a Python hello app in proj/main.py that prints 'Hello ISL-NANO', run it, and verify stdout and that main.py exists."):
    acts = LocalDesktopActuators("workspace_desktop")
    # Use the configurable provider; resolves to lmstudio_multistep by default
    # based on configs/llm.json (provider/model/parameters).
    provider = make_provider()
    adapter = LLMAdapter(provider)

    af_iters = 0
    steps_executed = 0
    first_fail_t = None

    context = {"user_intent": user_intent}

    with LOG_PATH.open("w", encoding="utf-8") as fp:
        ablation = get_ablation()
        log_event(fp, "config", {"ablation": ablation})
        emit_info(f"Ablation mode: {ablation}")
        
        # Sense → Arguments
        with span(fp, "sense"):
            log_event(fp, "sense", {"workspace": "workspace_desktop", "intent": user_intent})

        with span(fp, "reason", {"iter": af_iters, "phase":"nl_to_formal"}):
            llm_args, attacks = adapter.generate_arguments(context)
        # Normalize attacks
        if attacks is None:
            attacks = set()
        elif isinstance(attacks, set):
            pass
        else:
            _att_set = set()
            for e in attacks:
                if isinstance(e, (list, tuple)) and len(e) >= 2:
                    _att_set.add((e[0], e[1]))
                elif isinstance(e, dict) and "from" in e and "to" in e:
                    _att_set.add((e["from"], e["to"]))
            attacks = _att_set

        # (Optional) DEBUG failing verifier (keep commented in happy path)
        # for a in llm_args:
        #     if getattr(a.action, "name", None) == "run_proc":
        #         params = getattr(a.action, "params", {}) or {}
        #         cmd = params.get("cmd", ["python", "main.py"])
        #         cwd = params.get("cwd", ".")
        #         a.verify = {
        #             "verify_all": [
        #                 {"name":"proc_exitcode_ok","params":{"cmd":cmd,"cwd":cwd}},
        #                 {"name":"stdout_contains","params":{"cmd":cmd,"cwd":cwd,"must_include":"Hello-typo","timeout_s":5.0}}
        #             ]
        #         }
        #         break

        attack_edges = set((a[0], a[1]) for a in attacks)
        args = {a.id: a for a in llm_args}

        with span(fp, "reason", {"iter": af_iters, "phase":"solve"}):
            if is_no_priority():
                attacks_eff_current = attack_edges
            else:
                attacks_eff_current = filter_attacks_by_priority(args, attack_edges)

            if is_no_af():
                ext = set(args.keys())
                af = ArgFramework(args=args, attacks=set())
            else:
                af = ArgFramework(args=args, attacks=attacks_eff_current)
                ext = grounded_extension(af)
            af_iters += 1

        log_event(fp, "arguments_llm", {"ids": list(args.keys())})
        if attacks:
            log_event(fp, "attacks_llm", {"edges": list(list(x) for x in attacks)})

        log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
        steps = order_plan(af.args, ext)
        log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
        _export_tables(args, ext, attacks_eff_current, suffix=f"_iter{af_iters-1:02d}")

        # Simple fact set from filesystem
        facts = set()
        def pre_ok(pre): return all(p in facts for p in pre)
        def add_effects(effects): 
            for e in effects: facts.add(e)

        queue = list(steps); iters = 0; max_iters = len(queue)*4
        while queue and iters < max_iters:
            iters += 1
            step = queue.pop(0)
            a = af.args[step.arg_id]
            if not pre_ok(a.pre):
                queue.append(step); continue

            if a.action.name == "create_dir":
                with span(fp, "act", {"arg": a.id}):
                    p = a.action.params["path"]
                    res = acts.create_dir(p)
                    log_event(fp, "actuate", {"arg": a.id, "action": "create_dir", "params": a.action.params, "res": res})
                    steps_executed += 1
                add_effects(a.effects)
                if not _verify_all(acts.root, a.verify, fp):
                    if is_no_diag():
                        emit_fail("verify failed (no diagnosis)")
                        log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                        return
                    if first_fail_t is None: first_fail_t = time.perf_counter()
                    diag = _make_diag_arg(a, "verification_failed")
                    args[diag.id] = diag; attacks.add((diag.id, a.id))
                    with span(fp, "reason", {"iter": af_iters, "phase":"diagnosis"}):
                        attacks_eff = attacks if is_no_priority() else filter_attacks_by_priority(args, attacks)
                        af = ArgFramework(args=args, attacks=attacks_eff)
                        log_event(fp, "diagnosis", {"diag": diag.id, "attacks_add": [(diag.id, a.id)]})
                        ext = grounded_extension(af)
                        af_iters += 1
                    log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
                    steps = order_plan(af.args, ext)
                    log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
                    _export_tables(args, ext, attacks_eff, suffix=f"_iter{af_iters-1:02d}")
                    queue = list(steps); continue

            elif a.action.name == "write_file":
                with span(fp, "act", {"arg": a.id}):
                    p = a.action.params["path"]; content = a.action.params.get("content","")
                    res = acts.write_file(p, content)
                    log_event(fp, "actuate", {"arg": a.id, "action": "write_file", "params": {"path": p}, "res": res})
                    steps_executed += 1
                add_effects(a.effects)
                if not _verify_all(acts.root, a.verify, fp):
                    if is_no_diag():
                        emit_fail("verify failed (no diagnosis)")
                        log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                        return
                    if first_fail_t is None: first_fail_t = time.perf_counter()
                    diag = _make_diag_arg(a, "verification_failed")
                    args[diag.id] = diag; attacks.add((diag.id, a.id))
                    with span(fp, "reason", {"iter": af_iters, "phase":"diagnosis"}):
                        attacks_eff = attacks if is_no_priority() else filter_attacks_by_priority(args, attacks)
                        af = ArgFramework(args=args, attacks=attacks_eff)
                        log_event(fp, "diagnosis", {"diag": diag.id, "attacks_add": [(diag.id, a.id)]})
                        ext = grounded_extension(af)
                        af_iters += 1
                    log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
                    steps = order_plan(af.args, ext)
                    log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
                    _export_tables(args, ext, attacks_eff, suffix=f"_iter{af_iters-1:02d}")
                    queue = list(steps); continue

            elif a.action.name == "run_proc":
                cmd = list(a.action.params["cmd"])
                cwd = a.action.params.get("cwd", ".")
                # Normalize path duplication
                if cwd not in (".", "") and len(cmd) >= 2 and isinstance(cmd[1], str):
                    prefix = f"{cwd}/"
                    if cmd[1].startswith(prefix):
                        cmd[1] = cmd[1][len(prefix):]
                from pathlib import Path as _P
                target_dir = _P(acts.root, cwd).resolve()
                target_dir.mkdir(parents=True, exist_ok=True)
                if len(cmd) >= 2 and isinstance(cmd[1], str) and cmd[1].endswith("main.py"):
                    target_main = (target_dir / "main.py")
                    if not target_main.exists():
                        stray = None
                        for p in acts.root.rglob("main.py"):
                            stray = p; break
                        if stray and stray.exists():
                            target_dir.mkdir(parents=True, exist_ok=True)
                            target_main.write_text(stray.read_text(encoding="utf-8"), encoding="utf-8")
                            try: stray.unlink()
                            except Exception: pass
                with span(fp, "act", {"arg": a.id}):
                    res = acts.run_proc(cmd, cwd=cwd, timeout_s=120.0)
                    log_event(fp, "actuate", {"arg": a.id, "action": "run_proc", "params": {"cmd": cmd, "cwd": cwd}, "res": res})
                    steps_executed += 1
                if res["returncode"] != 0:
                    log_event(fp, "verify", {"check":"proc_exitcode_ok","status":"FAIL","returncode":res["returncode"]})
                    _export_tables(args, ext, attacks_eff_current, suffix=f"_iter{af_iters-1:02d}")
                    emit_fail("process failed")
                    log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                    return
                add_effects(a.effects)
                if not _verify_all(acts.root, a.verify, fp):
                    if is_no_diag():
                        emit_fail("verify failed (no diagnosis)")
                        log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                        return
                    if first_fail_t is None: first_fail_t = time.perf_counter()
                    diag = _make_diag_arg(a, "verification_failed")
                    args[diag.id] = diag; attacks.add((diag.id, a.id))
                    with span(fp, "reason", {"iter": af_iters, "phase":"diagnosis"}):
                        attacks_eff = attacks if is_no_priority() else filter_attacks_by_priority(args, attacks)
                        af = ArgFramework(args=args, attacks=attacks_eff)
                        log_event(fp, "diagnosis", {"diag": diag.id, "attacks_add": [(diag.id, a.id)]})
                        ext = grounded_extension(af)
                        af_iters += 1
                    log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
                    steps = order_plan(af.args, ext)
                    log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
                    _export_tables(args, ext, attacks_eff, suffix=f"_iter{af_iters-1:02d}")
                    queue = list(steps); continue

            elif a.action.name == "noop":
                with span(fp, "act", {"arg": a.id}):
                    log_event(fp, "actuate", {"arg": a.id, "action": "noop"})
                    steps_executed += 1
                if not _verify_all(acts.root, a.verify, fp):
                    if is_no_diag():
                        emit_fail("verify failed (no diagnosis)")
                        log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                        return
                    if first_fail_t is None: first_fail_t = time.perf_counter()
                    diag = _make_diag_arg(a, "verification_failed")
                    args[diag.id] = diag; attacks.add((diag.id, a.id))
                    with span(fp, "reason", {"iter": af_iters, "phase":"diagnosis"}):
                        attacks_eff = attacks if is_no_priority() else filter_attacks_by_priority(args, attacks)
                        af = ArgFramework(args=args, attacks=attacks_eff)
                        log_event(fp, "diagnosis", {"diag": diag.id, "attacks_add": [(diag.id, a.id)]})
                        ext = grounded_extension(af)
                        af_iters += 1
                    log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
                    steps = order_plan(af.args, ext)
                    log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
                    _export_tables(args, ext, attacks_eff, suffix=f"_iter{af_iters-1:02d}")
                    queue = list(steps); continue

            else:
                log_event(fp, "actuate", {"arg": a.id, "action": a.action.name, "status":"UNSUPPORTED"})
                _export_tables(args, ext, attacks_eff_current, suffix=f"_iter{af_iters-1:02d}")
                emit_fail(f"unsupported action:{a.action.name}")
                log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
                return

        if queue:
            iter_idx = globals().get("_af_iter", 0)
            _export_tables(args, ext, attacks_eff_current, suffix=f"_iter{iter_idx:02d}")
            globals()["_af_iter"] = iter_idx + 1
            emit_fail("unmet preconditions remain")
            log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
            return

        iter_idx = globals().get("_af_iter", 0)
        _export_tables(args, ext, attacks_eff_current, suffix=f"_iter{iter_idx:02d}")
        globals()["_af_iter"] = iter_idx + 1
        emit_ok(f"Desktop multistep LLM plan executed and verified. Log: {LOG_PATH}")
        log_metrics(fp, status="PASS", steps_to_success=steps_executed, af_iters=af_iters,
                    time_to_fix_s=(0.0 if first_fail_t is None else (time.perf_counter()-first_fail_t)))

def _run_one_check(acts_root, v):
    name = v.name if hasattr(v, "name") else v["name"]
    params = v.params if hasattr(v, "params") else v.get("params", {})

    def _norm_cmd_and_heal(cmd: list, cwd: str):
        from pathlib import Path as _P
        cmd2 = list(cmd)
        if cwd not in (".", "", None) and len(cmd2) >= 2 and isinstance(cmd2[1], str):
            prefix = f"{cwd}/"
            if cmd2[1].startswith(prefix):
                cmd2[1] = cmd2[1][len(prefix):]
        cwd_dir = _P(acts_root, cwd or ".").resolve()
        cwd_dir.mkdir(parents=True, exist_ok=True)
        if len(cmd2) >= 2 and isinstance(cmd2[1], str) and cmd2[1].endswith("main.py"):
            target_main = (cwd_dir / "main.py")
            if not target_main.exists():
                stray = None
                for p in _P(acts_root).rglob("main.py"):
                    stray = p; break
                if stray and stray.exists():
                    target_main.write_text(stray.read_text(encoding="utf-8"), encoding="utf-8")
                    try: stray.unlink()
                    except Exception: pass
        return cmd2, str(cwd_dir)

    if name == "noop":
        return {"check": "noop", "status": "PASS"}
    if name == "file_exists":
        tgt = Path(acts_root, params["path"])
        return file_exists(str(tgt), params.get("timeout_s", 5.0))
    if name == "file_hash_equal":
        tgt = Path(acts_root, params["path"])
        return file_hash_equal(str(tgt), params["expected_sha256"], params.get("timeout_s", 5.0))
    if name == "proc_exitcode_ok":
        cmd2, cwd2 = _norm_cmd_and_heal(params["cmd"], params.get("cwd", "."))
        return proc_exitcode_ok(cmd2, cwd=cwd2)
    if name == "stdout_contains":
        cmd2, cwd2 = _norm_cmd_and_heal(params["cmd"], params.get("cwd", "."))
        return stdout_contains(cmd2, cwd=cwd2, must_include=params["must_include"], timeout_s=params.get("timeout_s",30.0))
    if name == "stdout_regex":
        cmd2, cwd2 = _norm_cmd_and_heal(params["cmd"], params.get("cwd", "."))
        return stdout_regex(cmd2, cwd=cwd2, pattern=params["pattern"], timeout_s=params.get("timeout_s",30.0))
    if name == "json_field_equals":
        tgt = Path(acts_root, params["path"])
        return json_field_equals(str(tgt), params["pointer"], params["expected"])
    if name == "dir_contains":
        tgt = Path(acts_root, params["path"])
        return dir_contains(str(tgt), params.get("min_files", 1))
    if name == "file_glob_exists":
        root = Path(acts_root, params["root"])
        return file_glob_exists(str(root), params["pattern"])
    return {"check": name, "status": "SKIPPED"}

if __name__ == "__main__":
    main()
