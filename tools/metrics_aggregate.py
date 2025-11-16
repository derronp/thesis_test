#!/usr/bin/env python3
"""
metrics_aggregate.py
Read one or more JSONL run logs and emit:
  - runs/spans_long.csv     (one row per span record)
  - runs/metrics_long.csv   (one row per metrics record)
  - runs/summary_metrics.csv (grouped aggregates)
  - runs/summary_metrics.html (simple HTML table for thesis appendix)

Usage examples:
  python tools/metrics_aggregate.py --runs runs/isl_nano_run_*.jsonl
  python tools/metrics_aggregate.py --runs runs/isl_nano_run_desktop_*.jsonl runs/isl_nano_run_drone_*.jsonl
"""
from __future__ import annotations
import argparse, json, csv, statistics as stats
from pathlib import Path
from datetime import datetime

def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True,
                    help="One or more JSONL files (globs ok if shell expands)")
    args = ap.parse_args()

    outdir = Path("runs"); outdir.mkdir(parents=True, exist_ok=True)
    spans_csv   = outdir / "spans_long.csv"
    metrics_csv = outdir / "metrics_long.csv"
    summary_csv = outdir / "summary_metrics.csv"
    summary_html = outdir / "summary_metrics.html"

    spans_rows = []
    metrics_rows = []

    for p in args.runs:
        path = Path(p)
        if not path.exists():
            continue
        # Infer scenario/ablation from filename if present
        scenario = "unknown"
        if "overtemp" in path.name: scenario = "s1_overtemp"
        elif "overpressure" in path.name: scenario = "s1_overpressure"
        elif "drone" in path.name or "landing" in path.name: scenario = "s2_landing"
        elif "desktop" in path.name: scenario = "s3_desktop"

        # Look for an ablation tag in the file (many runs won’t have it; we default)
        ablation = "unknown"

        for rec in _read_jsonl(path):
            kind = rec.get("kind")
            ts = rec.get("ts")
            if ts is None:
                ts = 0.0
            if kind == "span":
                data = rec.get("data", {})
                spans_rows.append([
                    path.name, scenario, ablation,
                    ts, data.get("name",""), data.get("elapsed_s", None),
                    # carry optional tags if present
                    data.get("iter",""), data.get("phase",""), data.get("arg","")
                ])
            elif kind == "config":
                ablation = rec.get("data", {}).get("ablation", ablation)
            elif kind == "metrics":
                data = rec.get("data", {})
                metrics_rows.append([
                    path.name, scenario, ablation,
                    ts, data.get("status",""), data.get("steps_to_success",""),
                    data.get("af_iters",""), data.get("time_to_fix_s","")
                ])
            elif kind == "sense":
                # sometimes the ablation might be recorded here in future; left for extension
                pass

    # Write CSVs
    with spans_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["run_file","scenario","ablation","ts","span","elapsed_s","iter","phase","arg"])
        w.writerows(spans_rows)

    with metrics_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["run_file","scenario","ablation","ts","status","steps_to_success","af_iters","time_to_fix_s"])
        w.writerows(metrics_rows)

    # Aggregate summary (by scenario, status, ablation) — simple means
    # If you want ablation, record it in file names or add a 'config' event; for now it's 'unknown'.
    key = lambda r: (r[1], r[2])  # (scenario, ablation)
    buckets = {}
    for r in metrics_rows:
        k = key(r)
        buckets.setdefault(k, []).append(r)

    def _to_float(x):
        try:
            return float(x)
        except Exception:
            return None

    summary_rows = []
    for (scenario, ablation), rows in buckets.items():
        N = len(rows)
        statuses = [r[4] for r in rows]
        pass_rate = sum(1 for s in statuses if s == "PASS") / max(1, N)
        steps = [_to_float(r[5]) for r in rows if _to_float(r[5]) is not None]
        iters = [_to_float(r[6]) for r in rows if _to_float(r[6]) is not None]
        tfix  = [_to_float(r[7]) for r in rows if _to_float(r[7]) is not None and _to_float(r[7]) >= 0.0]
        def mean_or_blank(xs): 
            return round(stats.fmean(xs), 4) if xs else ""
        def sd_or_blank(xs):
            return round(stats.pstdev(xs), 4) if xs else ""

        summary_rows.append([
            scenario, ablation, N,
            round(pass_rate, 3),
            mean_or_blank(steps), sd_or_blank(steps),
            mean_or_blank(iters), sd_or_blank(iters),
            mean_or_blank(tfix), sd_or_blank(tfix),
        ])

    with summary_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow([
            "scenario","ablation","N","pass_rate",
            "steps_mean","steps_sd",
            "af_iters_mean","af_iters_sd",
            "time_to_fix_mean_s","time_to_fix_sd_s"
        ])
        w.writerows(summary_rows)

    # Lightweight HTML summary
    with summary_html.open("w", encoding="utf-8") as fp:
        fp.write("<!doctype html><meta charset='utf-8'>\n")
        fp.write(f"<h2>ISL-NANO Metrics Summary — {datetime.now().isoformat(timespec='seconds')}</h2>\n")
        fp.write("<style>table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 10px}</style>\n")
        fp.write("<table><thead><tr>")
        headers = ["scenario","ablation","N","pass_rate","steps_mean","steps_sd","af_iters_mean","af_iters_sd","time_to_fix_mean_s","time_to_fix_sd_s"]
        for h in headers: fp.write(f"<th>{h}</th>")
        fp.write("</tr></thead><tbody>\n")
        for row in summary_rows:
            fp.write("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>\n")
        fp.write("</tbody></table>\n")

    print(f"Wrote:\n  {spans_csv}\n  {metrics_csv}\n  {summary_csv}\n  {summary_html}")

if __name__ == "__main__":
    main()
