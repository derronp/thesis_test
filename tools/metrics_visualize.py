#!/usr/bin/env python3
"""
metrics_visualize.py

Generate thesis-ready plots from the CSVs produced by metrics_aggregate.py:
  - runs/summary_metrics.csv  (scenario-level aggregates)
  - runs/metrics_long.csv     (per-run metrics)
  - runs/spans_long.csv       (per-span timings; optional)

Outputs (under runs/plots/):
  - pass_rate_by_scenario.png
  - pass_rate_by_scenario_ablation.png
  - steps_hist_<scenario>_<ablation>.png
  - af_iters_hist_<scenario>_<ablation>.png
  - time_to_fix_hist_<scenario>_<ablation>.png
  - loop_latency_bar_<scenario>.png     (if spans_long.csv present)
  - index.html (thumbnail gallery)

Notes:
  * Uses matplotlib only, one chart per figure, no styles/colors specified.
  * Handles missing files/columns gracefully.
"""

from __future__ import annotations
import csv
from pathlib import Path
from collections import defaultdict, OrderedDict
import math

import matplotlib
matplotlib.use("Agg")  # headless safe
import matplotlib.pyplot as plt


RUNS = Path("runs")
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


def _to_int(x, default=None):
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except Exception:
        return default


def _ensure_plots_dir():
    PLOTS.mkdir(parents=True, exist_ok=True)


def _group_by(rows, keys):
    buckets = defaultdict(list)
    for r in rows:
        key = tuple(r.get(k, "") for k in keys)
        buckets[key].append(r)
    return buckets


def _save_bar(categories, values, title, ylabel, outfile):
    # categories: list[str], values: list[float]
    plt.figure()
    x = range(len(categories))
    plt.bar(x, values)
    plt.xticks(list(x), categories, rotation=30, ha="right")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(outfile, dpi=150, bbox_inches="tight")
    plt.close()


def _save_hist(values, title, xlabel, outfile, bins=20):
    plt.figure()
    plt.hist(values, bins=bins)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(outfile, dpi=150, bbox_inches="tight")
    plt.close()


def _save_bar_pairs(labels, series_dict, title, ylabel, outfile):
    """
    Stacked-by-label bars for multiple named series, aligned per label.
    series_dict: {series_name -> [values aligned to labels]}
    """
    plt.figure()
    x = list(range(len(labels)))
    width = 0.8 / max(1, len(series_dict))
    offset = -0.4 + width/2.0

    for i, (sname, vals) in enumerate(series_dict.items()):
        xi = [xx + offset + i*width for xx in x]
        plt.bar(xi, vals, width=width, label=sname)

    plt.xticks(x, labels, rotation=30, ha="right")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=150, bbox_inches="tight")
    plt.close()


def _mean(xs):
    xs2 = [v for v in xs if v is not None]
    if not xs2: return None
    return sum(xs2)/len(xs2)


def main():
    _ensure_plots_dir()

    summary = _read_csv(RUNS / "summary_metrics.csv")
    metrics = _read_csv(RUNS / "metrics_long.csv")
    spans   = _read_csv(RUNS / "spans_long.csv")  # optional

    # ---- 1) Pass rate by scenario (from summary) ----
    if summary:
        # Aggregate latest per (scenario, ablation); then take best per scenario (ablation 'none' prioritized)
        # Or simply bar by scenario using ablation=none where present.
        by_sa = _group_by(summary, ["scenario", "ablation"])
        # Build per-scenario dict preferring ablation='none'
        scenario_pass = {}
        for (sc, ab), rows in by_sa.items():
            # take the last row (should be unique anyway)
            r = rows[-1]
            pr = _to_float(r.get("pass_rate"), default=None)
            if pr is None: continue
            if sc not in scenario_pass:
                scenario_pass[sc] = {}
            scenario_pass[sc][ab] = pr

        # Single-bar per scenario (ablation none if exists else any)
        categories = []
        values = []
        for sc in sorted(scenario_pass.keys()):
            cats = scenario_pass[sc]
            if "none" in cats:
                pr = cats["none"]
            else:
                # fall back to any first value
                pr = list(cats.values())[0]
            categories.append(sc)
            values.append(pr)

        if categories:
            _save_bar(categories, values,
                      title="Pass Rate by Scenario (ablation=none)",
                      ylabel="pass rate",
                      outfile=PLOTS / "pass_rate_by_scenario.png")

        # Multi-bar per scenario: each ablation as a series
        # Build union of ablations
        all_abl = sorted({ab for sc in scenario_pass for ab in scenario_pass[sc].keys()})
        series = OrderedDict()
        for ab in all_abl:
            series[ab] = []
        labels = []
        for sc in sorted(scenario_pass.keys()):
            labels.append(sc)
            for ab in all_abl:
                series[ab].append(scenario_pass[sc].get(ab, 0.0))

        if labels:
            _save_bar_pairs(labels, series,
                            title="Pass Rate by Scenario and Ablation",
                            ylabel="pass rate",
                            outfile=PLOTS / "pass_rate_by_scenario_ablation.png")

    # ---- 2) Per-run distributions from metrics_long.csv ----
    if metrics:
        by_sa = _group_by(metrics, ["scenario", "ablation"])
        for (sc, ab), rows in by_sa.items():
            # Steps to success (only for PASS rows)
            steps = [_to_int(r.get("steps_to_success")) for r in rows if r.get("status") == "PASS"]
            steps = [s for s in steps if s is not None]
            if steps:
                _save_hist(
                    steps,
                    title=f"Steps to Success — {sc} ({ab})",
                    xlabel="steps",
                    outfile=PLOTS / f"steps_hist_{sc}_{ab}.png"
                )

            # AF iterations (all rows that have it)
            iters = [_to_int(r.get("af_iters")) for r in rows]
            iters = [v for v in iters if v is not None]
            if iters:
                _save_hist(
                    iters,
                    title=f"AF Iterations — {sc} ({ab})",
                    xlabel="iterations",
                    outfile=PLOTS / f"af_iters_hist_{sc}_{ab}.png"
                )

            # Time to fix (PASS rows that have it >= 0)
            tfix = [_to_float(r.get("time_to_fix_s")) for r in rows if r.get("status") == "PASS"]
            tfix = [v for v in tfix if v is not None and v >= 0.0]
            if tfix:
                _save_hist(
                    tfix,
                    title=f"Time to Fix — {sc} ({ab})",
                    xlabel="seconds",
                    outfile=PLOTS / f"time_to_fix_hist_{sc}_{ab}.png"
                )

    # ---- 3) Loop latency budgets from spans_long.csv ----
    if spans:
        # For each scenario, average elapsed_s by span name, then bar plot
        # Expected span names: sense, reason, act, verify (but robust to any)
        by_sc = _group_by(spans, ["scenario"])
        for (sc,), rows in by_sc.items():
            by_span = defaultdict(list)
            for r in rows:
                dt = _to_float(r.get("elapsed_s"))
                name = r.get("span", "")
                if dt is not None and name:
                    by_span[name].append(dt)
            # average per span
            labels = []
            vals = []
            for name in sorted(by_span.keys()):
                labels.append(name)
                vals.append(_mean(by_span[name]))
            if labels and any(v is not None for v in vals):
                # replace None with 0 for plotting
                vals = [v if v is not None else 0.0 for v in vals]
                _save_bar(labels, vals,
                          title=f"Loop Latency Budget — {sc}",
                          ylabel="seconds (mean)",
                          outfile=PLOTS / f"loop_latency_bar_{sc}.png")

    # ---- 4) Build a tiny HTML index of produced figures ----
    images = sorted([p for p in PLOTS.glob("*.png")])
    html = PLOTS / "index.html"
    with html.open("w", encoding="utf-8") as fp:
        fp.write("<!doctype html><meta charset='utf-8'>\n")
        fp.write("<style>body{font-family:sans-serif} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px} figure{margin:0} img{max-width:100%;height:auto;border:1px solid #ccc}</style>\n")
        fp.write("<h2>ISL-NANO Metrics — Plots</h2>\n")
        if images:
            fp.write("<div class='grid'>\n")
            for im in images:
                fp.write("<figure>")
                fp.write(f"<img src='{im.name}' alt='{im.name}'/>")
                fp.write(f"<figcaption>{im.name}</figcaption>")
                fp.write("</figure>\n")
            fp.write("</div>\n")
        else:
            fp.write("<p>No plots found. Did you run metrics_aggregate.py first?</p>")
    print(f"Wrote {len(images)} plots → {html}")


if __name__ == "__main__":
    main()
