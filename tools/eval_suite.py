#!/usr/bin/env python3
"""
eval_suite.py
Batch-run a scenario N times with a chosen ablation and write:
 - Per-run logs to runs/suite_<scenario>_<ablation>_<idx>.jsonl
 - A suite summary JSON to runs/suite_summary_<scenario>_<ablation>.json
Optionally call tools/metrics_aggregate.py to build CSV/HTML.

Usage examples:
  python tools/eval_suite.py --scenario s2_landing --ablation none --n 50
  python tools/eval_suite.py --scenario s1_overtemp --ablation no_diag --n 30 --seed 1337
  python tools/eval_suite.py --scenario s3_desktop_llm --n 10 --no-aggregate
"""
from __future__ import annotations
import argparse, json, os, subprocess, statistics as stats
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

SCENARIO_CMDS = {
    "s1_overtemp":      ["python", "-m", "demos.scenario1_overtemp"],
    "s1_overpressure":  ["python", "-m", "demos.scenario1_overpressure"],
    "s2_landing":       ["python", "-m", "demos.scenario2_landing"],
    "s3_desktop_llm":   ["python", "-m", "demos.scenario3_desktop_multistep_llm"],
}

def _extract_last_metrics(jsonl_path: Path) -> dict:
    try:
        last = None
        with jsonl_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("kind") == "metrics":
                    last = rec
        return last.get("data", {}) if last else {}
    except Exception:
        return {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True,
                    choices=list(SCENARIO_CMDS.keys()))
    ap.add_argument("--ablation", choices=["none","no_af","no_diag","no_priority"],
                    default="none")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42, help="Base seed (seed+i used per run)")
    ap.add_argument("--aggregate", dest="aggregate", action="store_true", default=True)
    ap.add_argument("--no-aggregate", dest="aggregate", action="store_false")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    cmd = SCENARIO_CMDS[args.scenario]

    print(f"=== Suite: {args.scenario}  ablation={args.ablation}  N={args.n} ===")

    log_paths = []
    pass_flags = []
    tfix_vals = []

    for i in range(args.n):
        log_path = RUNS / f"suite_{args.scenario}_{args.ablation}_{i:03d}.jsonl"
        env = os.environ.copy()
        env["ISL_LOG_PATH"] = str(log_path)
        env["ISL_ABLATION"] = args.ablation
        env["ISL_SEED"] = str(args.seed + i)  # scenarios can use this if desired

        # Run one trial
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True)
        log_paths.append(log_path)

        if not log_path.exists():
            pass_flags.append(False)
            continue

        m = _extract_last_metrics(log_path)
        pass_flags.append(m.get("status") == "PASS")
        if "time_to_fix_s" in m and m["time_to_fix_s"] is not None:
            try:
                tfix_vals.append(float(m["time_to_fix_s"]))
            except Exception:
                pass

        print(f"  [{i+1}/{args.n}] -> {'PASS' if pass_flags[-1] else 'FAIL'}  {log_path.name}")

    # Summaries
    total = len(pass_flags)
    pass_count = sum(1 for x in pass_flags if x)
    pass_rate = (pass_count / total) if total else 0.0
    tfix_mean = stats.fmean(tfix_vals) if tfix_vals else None
    tfix_sd   = stats.pstdev(tfix_vals) if len(tfix_vals) > 1 else (0.0 if tfix_vals else None)

    print("\n=== Suite summary ===")
    print(f"Pass rate: {pass_count}/{total} = {pass_rate:.3f}")
    if tfix_mean is not None:
        print(f"Time-to-fix mean: {tfix_mean:.3f} s (±{tfix_sd:.3f})")

    # Write suite summary JSON
    summary = {
        "scenario": args.scenario,
        "ablation": args.ablation,
        "n": args.n,
        "pass_rate": pass_rate,
        "time_to_fix_mean_s": tfix_mean,
        "time_to_fix_sd_s": tfix_sd,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "logs": [str(p) for p in log_paths],
    }
    out_json = RUNS / f"suite_summary_{args.scenario}_{args.ablation}.json"
    with out_json.open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)
    print(f"Saved summary: {out_json}")

    # Optional: aggregate the exact logs we produced
    if args.aggregate and log_paths:
        agg_script = ROOT / "tools" / "metrics_aggregate.py"
        if agg_script.exists():
            # Build explicit argv list because metrics_aggregate.py expects concrete paths
            argv = ["python", str(agg_script), "--runs", *[str(p) for p in log_paths]]
            print("Running aggregator:", " ".join(argv))
            subprocess.run(argv, cwd=str(ROOT), text=True)
        else:
            print("metrics_aggregate.py not found; skipping aggregation.")

if __name__ == "__main__":
    main()
