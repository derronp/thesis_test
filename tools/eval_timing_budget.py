#!/usr/bin/env python3
"""
eval_timing_budget.py

Compute realtime loop-latency budgets from spans_long.csv and emit:
  • runs/plots/loop_latency_budget_<scenario>[_<ablation>].png
  • runs/loop_latency_budget_<scenario>[_<ablation>].html
  • runs/loop_latency_budget_<scenario>[_<ablation>].csv

Works with the CSV produced by tools/metrics_aggregate.py.
It is robust to slight column name differences.

Usage examples:
  python tools/eval_timing_budget.py                      # all scenarios
  python tools/eval_timing_budget.py --scenario s2_landing
  python tools/eval_timing_budget.py --scenario s2_landing --ablation none
"""

from __future__ import annotations
import csv, math
from pathlib import Path
from collections import defaultdict, OrderedDict
import argparse

import matplotlib
matplotlib.use("Agg")  # headless-safe
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
PLOTS = RUNS / "plots"


def _read_csv(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fp:
        rdr = csv.DictReader(fp)
        for r in rdr:
            rows.append(r)
    return rows


def _to_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _ensure_outdirs():
    RUNS.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)


def _collect_columns(rows: list[dict]) -> dict[str, bool]:
    keys = set()
    for r in rows:
        keys.update(r.keys())
    present = {k: True for k in keys}
    return present


def _pick(r: dict, names: list[str], default=""):
    for n in names:
        if n in r and r[n] != "":
            return r[n]
    return default


def _group(rows: list[dict], keys: list[str]) -> dict[tuple, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[tuple(r.get(k, "") for k in keys)].append(r)
    return out


def _mean(xs):
    xs2 = [x for x in xs if x is not None]
    if not xs2:
        return None
    return sum(xs2) / len(xs2)


def _pstdev(xs):
    xs2 = [x for x in xs if x is not None]
    if not xs2:
        return None
    m = sum(xs2) / len(xs2)
    return math.sqrt(sum((x - m) ** 2 for x in xs2) / len(xs2))


def _save_bar(labels, values, title, ylabel, outfile):
    plt.figure()
    x = list(range(len(labels)))
    plt.bar(x, values)
    plt.xticks(x, labels, rotation=20, ha="right")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(outfile, dpi=150, bbox_inches="tight")
    plt.close()


def _write_html_table(path: Path, caption: str, rows: list[list[str]], header: list[str]):
    with path.open("w", encoding="utf-8") as fp:
        fp.write("<!doctype html><meta charset='utf-8'>\n")
        fp.write("<style>")
        fp.write("body{font-family:sans-serif} table{border-collapse:collapse}")
        fp.write("th,td{border:1px solid #ccc;padding:6px 8px;text-align:right}")
        fp.write("th:first-child,td:first-child{text-align:left}")
        fp.write("caption{font-weight:bold;margin-bottom:8px}")
        fp.write("</style>\n")
        fp.write(f"<table><caption>{caption}</caption>\n")
        fp.write("<thead><tr>")
        for h in header:
            fp.write(f"<th>{h}</th>")
        fp.write("</tr></thead>\n<tbody>\n")
        for r in rows:
            fp.write("<tr>")
            for c in r:
                fp.write(f"<td>{c}</td>")
            fp.write("</tr>\n")
        fp.write("</tbody></table>\n")


def _write_csv(path: Path, header: list[str], rows: list[list]):
    with path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def build_latency_budget(spans_rows: list[dict], scenario_filter: str|None, ablation_filter: str|None):
    """
    Build per-scenario (and per-ablation) latency budgets from per-span rows.
    We try to compute percentages via per-run totals when a run-id is present.
    Otherwise, we fall back to sum of mean(span) ≈ total_mean.
    """

    cols = _collect_columns(spans_rows)
    # Robust column names
    SCOL = "scenario"
    ACOL = "ablation" if "ablation" in cols else None
    SPAN_NAME_COL = "span" if "span" in cols else ("name" if "name" in cols else "phase")
    ELAPSED_COL = "elapsed_s"
    # Optional per-run identifier (varies depending on aggregator)
    RUNID_COL = None
    for c in ["run", "run_id", "source", "log", "file"]:
        if c in cols:
            RUNID_COL = c
            break

    # Filter by scenario/ablation if requested
    rows = []
    for r in spans_rows:
        sc = r.get(SCOL, "")
        ab = r.get(ACOL, "") if ACOL else ""
        if scenario_filter and sc != scenario_filter:
            continue
        if ablation_filter and ab != ablation_filter:
            continue
        rows.append(r)
    if not rows:
        return []

    # Group by (scenario, ablation)
    group_keys = [SCOL]
    if ACOL:
        group_keys.append(ACOL)
    grouped = _group(rows, group_keys)

    outputs = []  # list of (scenario, ablation, table_rows, plot_path, csv_path, html_path)

    for key, items in grouped.items():
        if len(group_keys) == 1:
            sc = key[0]
            ab = ""
        else:
            sc, ab = key

        # Build per-run totals if possible
        per_run_totals = defaultdict(float)  # run_id -> total seconds
        per_run_span_vals = defaultdict(lambda: defaultdict(list))  # run_id -> span -> [vals]

        for r in items:
            span_name = _pick(r, [SPAN_NAME_COL], "")
            dt = _to_float(r.get(ELAPSED_COL), default=None)
            if dt is None or not span_name:
                continue
            runid = r.get(RUNID_COL, None)
            if runid:
                per_run_totals[runid] += dt
                per_run_span_vals[runid][span_name].append(dt)

        span_names = sorted({ _pick(r, [SPAN_NAME_COL], "") for r in items if _pick(r, [SPAN_NAME_COL], "") })
        span_means = OrderedDict()
        span_sds   = OrderedDict()
        span_perc  = OrderedDict()

        if RUNID_COL and per_run_totals:
            # Compute per-run mean for each span, then percentage relative to that run's total
            per_span_pct_samples = defaultdict(list)  # span -> [pct samples]
            per_span_means = defaultdict(list)        # span -> [mean per run]
            for runid, total in per_run_totals.items():
                if total <= 0:
                    continue
                for span in span_names:
                    vals = per_run_span_vals[runid].get(span, [])
                    if not vals:
                        continue
                    mean_span_this_run = sum(vals)/len(vals)
                    per_span_means[span].append(mean_span_this_run)
                    per_span_pct_samples[span].append(100.0 * mean_span_this_run / total)

            for span in span_names:
                m = _mean(per_span_means.get(span, []))
                sd = _pstdev(per_span_means.get(span, []))
                p = _mean(per_span_pct_samples.get(span, []))
                span_means[span] = m if m is not None else 0.0
                span_sds[span]   = sd if sd is not None else 0.0
                span_perc[span]  = p if p is not None else 0.0
        else:
            # Fallback: compute mean per span, then percentage from sum of mean spans
            per_span_vals = defaultdict(list)
            for r in items:
                span_name = _pick(r, [SPAN_NAME_COL], "")
                dt = _to_float(r.get(ELAPSED_COL), default=None)
                if dt is not None and span_name:
                    per_span_vals[span_name].append(dt)
            total_mean = 0.0
            for span in span_names:
                m = _mean(per_span_vals.get(span, [])) or 0.0
                sd = _pstdev(per_span_vals.get(span, [])) or 0.0
                span_means[span] = m
                span_sds[span] = sd
                total_mean += m
            for span in span_names:
                span_perc[span] = (100.0 * span_means[span] / total_mean) if total_mean > 0 else 0.0

        # Emit CSV table
        suffix = f"_{sc}" + (f"_{ab}" if ab else "")
        csv_path  = RUNS  / f"loop_latency_budget{suffix}.csv"
        html_path = RUNS  / f"loop_latency_budget{suffix}.html"
        png_path  = PLOTS / f"loop_latency_budget{suffix}.png"

        rows_out = []
        for span in span_names:
            rows_out.append([
                span,
                f"{span_means[span]:.6f}",
                f"{span_sds[span]:.6f}",
                f"{span_perc[span]:.2f}"
            ])
        _write_csv(csv_path, header=["phase", "mean_s", "stddev_s", "percent_of_loop"], rows=rows_out)

        # HTML table
        title = f"Loop Latency Budget — {sc}" + (f" ({ab})" if ab else "")
        _write_html_table(html_path, title, rows_out,
                          header=["Phase", "Mean (s)", "StdDev (s)", "% of loop"])

        # Plot (bar on mean seconds)
        labels = [r[0] for r in rows_out]
        vals   = [float(r[1]) for r in rows_out]
        _save_bar(labels, vals, title=title, ylabel="seconds (mean)", outfile=png_path)

        outputs.append((sc, ab, csv_path, html_path, png_path))

    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=None, help="Filter by scenario id (e.g., s2_landing)")
    ap.add_argument("--ablation", default=None, help="Filter by ablation label (e.g., none)")
    args = ap.parse_args()

    _ensure_outdirs()
    spans_rows = _read_csv(RUNS / "spans_long.csv")
    if not spans_rows:
        print("No runs/spans_long.csv found. Run metrics_aggregate.py or eval_suite.py first.")
        return

    outputs = build_latency_budget(spans_rows, args.scenario, args.ablation)
    if not outputs:
        print("No matching rows for the given filters.")
        return

    print("Generated timing budgets:")
    for sc, ab, csvp, htmlp, pngp in outputs:
        label = f"{sc}" + (f" ({ab})" if ab else "")
        print(f"  - {label}")
        print(f"      CSV:  {csvp}")
        print(f"      HTML: {htmlp}")
        print(f"      PNG:  {pngp}")


if __name__ == "__main__":
    main()
