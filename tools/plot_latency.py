#!/usr/bin/env python3
"""
plot_latency.py
Read runs/spans_long.csv and create per-span histograms.
"""
import csv
from pathlib import Path
import matplotlib.pyplot as plt
from collections import defaultdict

def main():
    p = Path("runs/spans_long.csv")
    if not p.exists():
        print("spans_long.csv not found. Run metrics_aggregate.py first.")
        return
    by_span = defaultdict(list)
    with p.open("r", encoding="utf-8") as fp:
        rdr = csv.DictReader(fp)
        for row in rdr:
            name = row["span"]
            try:
                dt = float(row["elapsed_s"])
            except:
                continue
            by_span[name].append(dt)

    outdir = Path("runs"); outdir.mkdir(parents=True, exist_ok=True)
    for span_name, vals in by_span.items():
        if not vals: continue
        plt.figure()
        plt.hist(vals, bins=20)
        plt.title(f"Latency Histogram — {span_name}")
        plt.xlabel("seconds"); plt.ylabel("count")
        out = outdir / f"latency_{span_name}.png"
        plt.savefig(out, dpi=150, bbox_inches="tight")
        plt.close()
        print("Wrote:", out)

if __name__ == "__main__":
    main()
