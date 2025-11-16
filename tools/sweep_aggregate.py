
#!/usr/bin/env python3
"""
Aggregate plots for Scenario 2 sweep results.

Inputs:
- runs/drone_sweep_results.csv (from tools/sweep_drone.py)

Outputs:
- runs/drone_sweep_success_vs_gust.png       (success rate vs gust_amp, averaged over vx)
- runs/drone_sweep_ttd_vs_vx.png             (avg touchdown time vs vx, successes only, averaged over gust_amp)
- runs/drone_sweep_policy_rate_vs_gust.png   (fraction of conservative final policy vs gust_amp)
- runs/drone_sweep_agg.csv                   (tabular aggregates per gust & per vx)

Rules:
- matplotlib only
- one chart per figure
- no custom colors/styles
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
import matplotlib.pyplot as plt

# --- repo-root import shim ---
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# ------------------------------

RUNS = Path("runs")
SRC  = RUNS/"drone_sweep_results.csv"

def read_rows():
    if not SRC.exists():
        print("No sweep results found:", SRC); return []
    rows = []
    with SRC.open("r", encoding="utf-8") as fp:
        r = csv.DictReader(fp)
        for row in r:
            try:
                rows.append({
                    "vx": float(row["vx"]),
                    "gust_amp": float(row["gust_amp"]),
                    "policy_initial": row.get("policy_initial",""),
                    "policy_final": row.get("policy_final",""),
                    "success": int(row["success"]),
                    "t_touchdown": float(row["t_touchdown"]),
                    "vmag": float(row["vmag"]),
                })
            except Exception:
                continue
    return rows

def group_by(rows, key):
    d = {}
    for r in rows:
        k = r[key]
        d.setdefault(k, []).append(r)
    keys = sorted(d.keys())
    return keys, d

def agg_success_rate(v):
    if not v: return float("nan")
    return sum(r["success"] for r in v) / len(v)

def agg_policy_rate_conservative(v):
    if not v: return float("nan")
    cons = sum(1 for r in v if r.get("policy_final","") == "conservative")
    return cons / len(v)

def agg_ttd_success_only(v):
    t = [r["t_touchdown"] for r in v if r["success"] == 1]
    return (sum(t)/len(t)) if t else float("nan")

def write_agg_csv(per_gust, per_vx):
    out = RUNS/"drone_sweep_agg.csv"
    with out.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["section","key","success_rate","policy_rate_conservative","avg_touchdown_time_successes_only"])
        for k, vals in per_gust.items():
            w.writerow(["by_gust_amp", f"{k:.4f}", 
                        agg_success_rate(vals),
                        agg_policy_rate_conservative(vals),
                        agg_ttd_success_only(vals)])
        for k, vals in per_vx.items():
            w.writerow(["by_vx", f"{k:.4f}", 
                        agg_success_rate(vals),
                        agg_policy_rate_conservative(vals),
                        agg_ttd_success_only(vals)])
    print("Wrote:", out)

def plot_success_vs_gust(keys, groups):
    y = [agg_success_rate(groups[k]) for k in keys]
    plt.figure()
    plt.plot(keys, y, marker="o")
    plt.xlabel("gust amplitude (m/s)"); plt.ylabel("success rate"); plt.title("Success rate vs gust amplitude")
    plt.ylim(0, 1)
    out = RUNS/"drone_sweep_success_vs_gust.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); print("Wrote:", out)

def plot_ttd_vs_vx(keys, groups):
    y = [agg_ttd_success_only(groups[k]) for k in keys]
    plt.figure()
    plt.plot(keys, y, marker="o")
    plt.xlabel("wind vx (m/s)"); plt.ylabel("avg touchdown time (s) — successes only"); plt.title("Avg touchdown time vs wind vx")
    out = RUNS/"drone_sweep_ttd_vs_vx.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); print("Wrote:", out)

def plot_policy_rate_vs_gust(keys, groups):
    y = [agg_policy_rate_conservative(groups[k]) for k in keys]
    plt.figure()
    plt.plot(keys, y, marker="o")
    plt.xlabel("gust amplitude (m/s)"); plt.ylabel("fraction conservative chosen"); plt.title("Final policy rate vs gust amplitude")
    plt.ylim(0, 1)
    out = RUNS/"drone_sweep_policy_rate_vs_gust.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); print("Wrote:", out)

def main():
    rows = read_rows()
    if not rows:
        return
    gust_keys, by_gust = group_by(rows, "gust_amp")
    vx_keys, by_vx     = group_by(rows, "vx")

    plot_success_vs_gust(gust_keys, by_gust)
    plot_ttd_vs_vx(vx_keys, by_vx)
    plot_policy_rate_vs_gust(gust_keys, by_gust)

    write_agg_csv(by_gust, by_vx)

if __name__ == "__main__":
    main()
