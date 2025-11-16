from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Iterable, Tuple
import csv, math, json, time, os, sys

from core.arguments import ArgFramework, Argument, ActionSpec, VerifySpec
from core.af_solver import grounded_extension, filter_attacks_by_priority
from core.planner import order_plan
from core.logging_utils import log_event, export_csv, summarize_sources
from core.logging_utils import span, log_metrics
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info, emit_line
from core.ablation import is_no_af, is_no_diag, is_no_priority, get_ablation
enable_utf8_stdout()

from domains.drone.model import DroneSim, DroneState, Wind, policy_aggressive, policy_conservative
from domains.drone.rules import generate_landing_AF

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os

# ...
LOG_PATH = Path(os.environ.get("ISL_LOG_PATH", "runs/isl_nano_run_drone_landing.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------

def _export_tables(args, ext, attacks_eff_current, suffix=""):
    try:
        from core.logging_utils import export_csv as _exp
    except Exception:
        def _exp(path, rows, header):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as fp:
                w = csv.writer(fp); w.writerow(header); w.writerows(rows)

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
    _exp(outdir / f"af_selection{suffix}.csv", rows,
         ["arg_id","status","priority","topic","action","source","role"])

    rows2 = []
    for e in (attacks_eff_current or []):
        try: x,y = e
        except: continue
        rows2.append([x,y])
    _exp(outdir / f"af_attacks{suffix}.csv", rows2, ["attacker","target"])

    src_rows = summarize_sources(args, acc, attacks_eff_current)
    if src_rows:
        _exp(outdir / f"af_sources{suffix}.csv", src_rows,
             ["source","role","total_args","accepted","rejected","acceptance_rate","attacks_out","attacks_in"])

def _append_verifier_stats(detail: dict, *, policy: str, wind, bounds: dict, seed=None, csv_path=Path("runs/drone_verifier_stats.csv")):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "ts_unix","policy","seed",
        "wind_vx","wind_gust_amp","wind_gust_period",
        "zone_r","max_speed","max_time",
        "in_zone","speed_ok","time_ok",
        "vmag","t_touchdown"
    ]
    row = [
        int(time.time()), policy, (seed if seed is not None else ""),
        getattr(wind, "vx", ""), getattr(wind, "gust_amp", ""), getattr(wind, "gust_period", ""),
        bounds.get("zone_r",""), bounds.get("max_speed",""), bounds.get("max_time",""),
        detail.get("in_zone",""), detail.get("speed_ok",""), detail.get("time_ok",""),
        detail.get("vmag",""), detail.get("t_touchdown",""),
    ]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        if write_header:
            w.writerow(header)
        w.writerow(row)

def simulate(policy_name: str, wind: Wind, seed: int|None=None) -> Dict[str, Any]:
    sim = DroneSim(dt=0.05, max_time=20.0, wind=wind)
    if seed is not None:
        import random; random.seed(seed)
    sim.reset(DroneState())
    if policy_name == "aggressive":
        res = sim.run_policy(policy_aggressive)
    else:
        res = sim.run_policy(policy_conservative)
    return res

def verify_after_sim(res: Dict[str,Any], zone_r: float, max_speed: float, max_time: float) -> Tuple[bool, Dict[str,Any]]:
    traj = res["traj"]
    final = res["final"]
    t_td = res["touchdown_time"]
    in_zone = abs(final["x"]) <= zone_r and final["y"] == 0.0
    vmag = math.sqrt(final["vx"]**2 + final["vy"]**2)
    speed_ok = vmag <= max_speed
    time_ok = t_td <= max_time
    ok = in_zone and speed_ok and time_ok
    detail = {"in_zone": in_zone, "speed_ok": speed_ok, "vmag": vmag, "time_ok": time_ok, "t_touchdown": t_td}
    return ok, detail

def main(wind=Wind(vx=0.8, gust_amp=0.3, gust_period=5.0), seed=42):
    af_iters = 0
    steps_executed = 0
    first_fail_t = None

    with LOG_PATH.open("w", encoding="utf-8") as fp:
        ablation = get_ablation()
        log_event(fp, "config", {"ablation": ablation})
        emit_info(f"Ablation mode: {ablation}")
        
        # Sense → Arguments
        with span(fp, "sense"):
            log_event(fp, "sense", {"scenario":"drone_landing", "wind": wind.__dict__})

        # 1) Build AF (reason)
        with span(fp, "reason", {"iter": af_iters}):
            af0 = generate_landing_AF(zone_radius=1.5, max_speed=0.6, max_time=20.0)
            args = af0.args.copy()

            if is_no_priority():
                attacks_eff = set(af0.attacks)
            else:
                attacks_eff = filter_attacks_by_priority(args, af0.attacks)

            if is_no_af():
                ext = set(args.keys())
                af = ArgFramework(args=args, attacks=set())
            else:
                af = ArgFramework(args=args, attacks=attacks_eff)
                ext = grounded_extension(af)
            af_iters += 1

            log_event(fp, "arguments", {"ids": list(args.keys()), "attacks": list(map(list, af.attacks))})
            log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
            steps = order_plan(af.args, ext)
            log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
            _export_tables(args, ext, af.attacks, suffix=f"_iter{af_iters-1:02d}")

        # 2) Execute (select policy)
        policy = None
        for s in steps:
            a = af.args[s.arg_id]
            if isinstance(a.action, ActionSpec) and a.action.name == "set_policy":
                policy = a.action.params.get("name")
                with span(fp, "act", {"arg": a.id}):
                    log_event(fp, "actuate", {"arg": a.id, "action": "set_policy", "params": {"name": policy}})
                    steps_executed += 1
                break

        if policy is None:
            emit_fail(f"no policy in plan. Log: {LOG_PATH}")
            log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters)
            return

        # 3) Simulate + verify attempt 1
        with span(fp, "act", {"phase": "simulate"}):
            res = simulate(policy, wind, seed=seed)
        log_event(fp, "simulate", {"policy": policy, "summary": {"t": res["touchdown_time"], "final": res["final"]}})

        any_arg = args["A_policy_aggr"]
        v = any_arg.verify.params

        with span(fp, "verify", {"phase": "attempt1"}):
            ok, detail = verify_after_sim(res, v["zone_r"], v["max_speed"], v["max_time"])
        log_event(fp, "verify", {"check":"after_sim_verify_all", "status":"PASS" if ok else "FAIL", "detail": detail})
        _append_verifier_stats(detail, policy=policy, wind=wind,
                               bounds={"zone_r": v["zone_r"], "max_speed": v["max_speed"], "max_time": v["max_time"]},
                               seed=seed)

        if ok or is_no_diag():
            if ok:
                emit_ok(f"Drone landing verified with policy: {policy}")
            else:
                emit_fail(f"Landing verification failed (no diagnosis). Log: {LOG_PATH}")
            log_metrics(fp, status=("PASS" if ok else "FAIL"),
                        steps_to_success=steps_executed, af_iters=af_iters,
                        time_to_fix_s=(0.0 if first_fail_t is None else (time.perf_counter()-first_fail_t)))
            Path("runs/drone_traj.json").write_text(json.dumps(res["traj"]), encoding="utf-8")
            emit_line(f"Log: {LOG_PATH}")
            emit_line("Trajectory: runs/drone_traj.json")
            return

        # 4) Diagnosis pass (reason + act + verify attempt 2)
        first_fail_t = time.perf_counter()

        chosen = "A_policy_aggr" if policy == "aggressive" else "A_policy_cons"
        other  = "A_policy_cons" if policy == "aggressive" else "A_policy_aggr"
        diag_id = f"D_{chosen}"

        with span(fp, "reason", {"iter": af_iters}):
            args[diag_id] = Argument(
                id=diag_id, domain="drone", topic="diagnosis",
                pre=tuple(), action=ActionSpec("noop", {}), effects=tuple(),
                verify=VerifySpec("noop", {}), priority=getattr(args[chosen], "priority", 0) + 2,
                source="drone_diag", role="diagnosis",
            )
            attacks = set(af.attacks); attacks.add((diag_id, chosen))
            if is_no_priority():
                attacks_eff2 = attacks
            else:
                attacks_eff2 = filter_attacks_by_priority(args, attacks)
            af = ArgFramework(args=args, attacks=attacks_eff2)
            ext = grounded_extension(af)
            af_iters += 1

            log_event(fp, "diagnosis", {"diag": diag_id, "attacks_add": [(diag_id, chosen)]})
            log_event(fp, "grounded_extension", {"accepted": sorted(list(ext))})
            steps = order_plan(af.args, ext)
            log_event(fp, "plan", {"steps": [s.arg_id for s in steps]})
            _export_tables(args, ext, af.attacks, suffix=f"_iter{af_iters-1:02d}")

        policy = "conservative" if policy == "aggressive" else "aggressive"
        with span(fp, "act", {"phase": "simulate2"}):
            log_event(fp, "actuate", {"arg": f"{other}", "action": "set_policy", "params": {"name": policy}})
            steps_executed += 1
            res = simulate(policy, wind, seed=seed)
        log_event(fp, "simulate", {"policy": policy, "summary": {"t": res["touchdown_time"], "final": res["final"]}})

        with span(fp, "verify", {"phase": "attempt2"}):
            ok2, detail2 = verify_after_sim(res, v["zone_r"], v["max_speed"], v["max_time"])
        log_event(fp, "verify", {"check":"after_sim_verify_all", "status":"PASS" if ok2 else "FAIL", "detail": detail2})
        _append_verifier_stats(detail2, policy=policy, wind=wind,
                               bounds={"zone_r": v["zone_r"], "max_speed": v["max_speed"], "max_time": v["max_time"]},
                               seed=seed)

        Path("runs/drone_traj.json").write_text(json.dumps(res["traj"]), encoding="utf-8")

        if not ok2:
            emit_fail(f"Landing verification failed. Log: {LOG_PATH}")
            log_metrics(fp, status="FAIL", steps_to_success=steps_executed, af_iters=af_iters,
                        time_to_fix_s=(time.perf_counter()-first_fail_t))
            return

        emit_ok(f"Drone landing verified with policy: {policy}")
        emit_line(f"Log: {LOG_PATH}")
        emit_line("Trajectory: runs/drone_traj.json")
        log_metrics(fp, status="PASS", steps_to_success=steps_executed, af_iters=af_iters,
                    time_to_fix_s=(time.perf_counter()-first_fail_t if first_fail_t else 0.0))

if __name__ == "__main__":
    main()
