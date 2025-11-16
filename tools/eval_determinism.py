#!/usr/bin/env python3
"""
eval_determinism.py
Run a given scenario multiple times and measure repeatability
of grounded extensions and PASS/FAIL metrics.

Usage:
  python tools/eval_determinism.py --scenario s2_landing --n 50
  python tools/eval_determinism.py --scenario s1_overtemp --n 30
"""

from __future__ import annotations
import argparse, json, subprocess, hashlib, statistics as stats, os
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

def _hash_json(obj) -> str:
    s = json.dumps(obj, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

def _extract_grounded_hash(path: Path) -> str:
    """Return hash of the last grounded_extension record in a JSONL file."""
    try:
        with path.open("r", encoding="utf-8") as fp:
            last = None
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("kind") == "grounded_extension":
                    last = rec
        if not last:
            return ""
        accepted = last.get("data", {}).get("accepted", [])
        return _hash_json(sorted(accepted))
    except Exception:
        return ""

def _extract_metrics(path: Path) -> dict:
    """Return last metrics record (if any) from the log file."""
    try:
        with path.open("r", encoding="utf-8") as fp:
            last = None
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
                    choices=list(SCENARIO_CMDS.keys()),
                    help="Scenario ID to test determinism on.")
    ap.add_argument("--n", type=int, default=10, help="Number of runs")
    ap.add_argument("--seed", type=int, default=42, help="Base seed")
    ap.add_argument("--ablation", choices=["none","no_af","no_diag","no_priority"], default="none",
                    help="Optional ablation to set during runs")
    args = ap.parse_args()

    print(f"=== Determinism test for {args.scenario} ({args.n} runs) — ablation={args.ablation} ===")

    RUNS.mkdir(parents=True, exist_ok=True)

    hashes = []
    tfix_vals = []
    passes = 0
    failures = []

    for i in range(args.n):
        log_path = RUNS / f"det_{args.scenario}_{i:03d}.jsonl"
        env = os.environ.copy()
        env["ISL_LOG_PATH"] = str(log_path)           # <-- tell scenario where to write
        env["ISL_SEED"] = str(args.seed + i)          # if scenario uses seeds
        env["ISL_ABLATION"] = args.ablation           # ensure ablation is labeled in logs

        cmd = SCENARIO_CMDS[args.scenario]
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True)

        if not log_path.exists():
            failures.append((i, "log not written"))
            continue

        ghash = _extract_grounded_hash(log_path)
        hashes.append(ghash)
        mets = _extract_metrics(log_path)
        if mets.get("status") == "PASS":
            passes += 1
        tfix = mets.get("time_to_fix_s", None)
        try:
            if tfix is not None:
                tfix_vals.append(float(tfix))
        except Exception:
            pass

    # Determinism ratio
    if not hashes:
        print("No logs found; check scenario and paths.")
        return
    base = hashes[0]
    identical = sum(1 for h in hashes if h == base)
    ratio = identical / len(hashes)

    # Summaries
    pass_rate = passes / len(hashes)
    tfix_mean = stats.fmean(tfix_vals) if tfix_vals else None
    tfix_sd   = stats.pstdev(tfix_vals) if len(tfix_vals) > 1 else 0.0 if tfix_vals else None

    print(f"\nDeterminism ratio: {identical}/{len(hashes)} = {ratio:.3f}")
    print(f"Pass rate:         {passes}/{len(hashes)} = {pass_rate:.3f}")
    if tfix_mean is not None:
        print(f"Time-to-fix mean:  {tfix_mean:.3f} s (±{tfix_sd:.3f})")
    if failures:
        print("\nRuns without logs:")
        for i, why in failures:
            print(f"  #{i:03d}: {why}")

    # Save summary JSON
    summary = {
        "scenario": args.scenario,
        "n": args.n,
        "ablation": args.ablation,
        "ratio_determinism": ratio,
        "pass_rate": pass_rate,
        "time_to_fix_mean_s": tfix_mean,
        "time_to_fix_sd_s": tfix_sd,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    out_json = RUNS / f"determinism_{args.scenario}_{args.ablation}.json"
    with out_json.open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)
    print(f"\nSaved summary: {out_json}")

if __name__ == "__main__":
    main()
