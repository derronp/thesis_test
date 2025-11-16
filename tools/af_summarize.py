
#!/usr/bin/env python3
# tools/af_summarize.py
import argparse, json
from pathlib import Path
from html import escape

# -------------------------
# IO helpers
# -------------------------
def read_jsonl(path: Path):
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            try:
                import ast
                events.append(ast.literal_eval(line))
            except Exception:
                events.append({"kind": "raw", "data": line})
    return events


def list_iter_csvs(run_dir: Path, prefix: str):
    return sorted(run_dir.glob(f"{prefix}_iter*.csv"))


def read_csv_rows(path: Path):
    rows = []
    if not path.exists():
        return rows
    txt = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not txt:
        return rows
    head = [c.strip() for c in txt[0].split(",")];
    for ln in txt[1:]:
        if not ln.strip():
            continue
        parts = [c.strip() for c in ln.split(",")];
        rows.append(dict(zip(head, parts)))
    return rows


def iter_index_from_name(p: Path):
    # expects ..._iterNN.csv
    name = p.name
    try:
        idx = int(name.split("_iter")[-1].split(".csv")[0])
        return idx
    except Exception:
        return None

# -------------------------
# Event mining (reasons)
# -------------------------
def collect_from_jsonl(events):
    accepted = None
    all_ge = []
    attacks_with_reasons = []
    for ev in events:
        if ev.get("kind") == "grounded_extension":
            acc = ev.get("data", {}).get("accepted", [])
            all_ge.append(acc)
            accepted = acc
        elif ev.get("kind") == "diagnosis":
            d = ev.get("data", {})
            add = d.get("attacks_add", [])
            for pair in add:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    attacks_with_reasons.append(
                        {"from": pair[0], "to": pair[1], "reason": "verification_failed/diagnosis"}
                    )
    return accepted or [], all_ge, attacks_with_reasons


def collect_attacks_from_events(events):
    out = []
    for ev in events:
        if ev.get("kind") in ("arguments_llm", "arguments"):
            d = ev.get("data", {})
            atk = d.get("attacks") or d.get("edges") or []
            for e in atk:
                if isinstance(e, dict):
                    out.append({"from": e.get("from", ""), "to": e.get("to", ""), "reason": e.get("reason", "")})
                elif isinstance(e, (list, tuple)) and len(e) >= 2:
                    out.append({"from": e[0], "to": e[1], "reason": ""})
    return out


def unique_edges(edges):
    seen = set()
    res = []
    for e in edges:
        key = (e.get("from", ""), e.get("to", ""), e.get("reason", ""))
        if key in seen:
            continue
        seen.add(key)
        res.append(e)
    return res

# -------------------------
# Rendering
# -------------------------
def _table(headers, rows):
    th = "".join(f"<th>{escape(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = "".join(f"<td>{escape(str(r.get(h, '')))}</td>" for h in headers)
        trs.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def _attach_reasons(att_rows, reason_edges):
    reason_map = {(e["from"], e["to"]): e.get("reason", "") for e in reason_edges}
    merged = []
    for r in att_rows:
        merged.append({
            "attacker": r.get("attacker", ""),
            "target": r.get("target", ""),
            "reason": reason_map.get((r.get("attacker", ""), r.get("target", "")), "")
        })
    return merged


def render_html(run_name, events, final_selection_rows, final_attacks_rows,
                final_source_rows, sel_iters, att_iters, src_iters, edge_reasons, run_dir: Path):
    css = """
    <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;padding:24px;max-width:1100px;margin:auto;background:#fff;}
    h1{font-size:22px;margin:0 0 12px;}
    h2{font-size:18px;margin:24px 0 8px;}
    h3{font-size:16px;margin:18px 0 6px;}
    table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 16px;}
    th,td{border:1px solid #ddd;padding:6px 8px;}
    th{background:#f5f6f7;text-align:left;}
    .muted{color:#667;}
    .iter{margin:8px 0 22px;}
    .plots img{max-width:100%;height:auto;margin:8px 0;border:1px solid #eee;}
    figure{margin:8px 0;}
    figcaption{font-size:12px;color:#667;}
    .files a{margin-right:16px;}
    </style>
    """
    html_parts = [
        f"<!doctype html><meta charset='utf-8'><title>AF Summary - {escape(run_name)}</title>{css}",
        f"<h1>ISL-NANO AF Summary — {escape(run_name)}</h1>",
    ]

    # Final selection
    html_parts.append("<h2>Final selection (accepted vs rejected)</h2>")
    if final_selection_rows:
        headers = ["arg_id", "status", "priority", "topic", "action", "source", "role"]
        html_parts.append(_table(headers, final_selection_rows))
    else:
        html_parts.append("<p class='muted'>No selection CSV found.</p>")

    # Final attacks (with reasons)
    html_parts.append("<h2>Effective attacks (priority-filtered)</h2>")
    if final_attacks_rows:
        merged = _attach_reasons(final_attacks_rows, edge_reasons)
        headers = ["attacker", "target", "reason"]
        html_parts.append(_table(headers, merged))
    else:
        html_parts.append("<p class='muted'>No effective attacks CSV found.</p>")

    # Per-source summary
    html_parts.append("<h2>Agent/source contributions</h2>")
    if final_source_rows:
        headers = ["source","role","total_args","accepted","rejected","acceptance_rate","attacks_out","attacks_in"]
        html_parts.append(_table(headers, final_source_rows))
    else:
        html_parts.append("<p class='muted'>No source summary CSV found.</p>")

    # Trajectory plots (single run)
    html_parts.append("<h2>Trajectory plots</h2>")
    traj_imgs = [
        run_dir/"drone_altitude_time.png",
        run_dir/"drone_vy_time.png",
        run_dir/"drone_x_time.png",
        run_dir/"drone_speed_time.png",
    ]
    have_any = False
    html_parts.append("<div class='plots'>")
    for im in traj_imgs:
        if im.exists():
            have_any = True
            html_parts.append(f"<figure><img src='{escape(im.name)}'><figcaption>{escape(im.name)}</figcaption></figure>")
    html_parts.append("</div>")
    if not have_any:
        html_parts.append("<p class='muted'>No trajectory plots found. Run: <code>python tools/plot_drone_metrics.py</code></p>")

    # Per-iteration tables
    html_parts.append("<h2>Per-iteration snapshots (embedded)</h2>")
    if sel_iters:
        att_map = {iter_index_from_name(p): p for p in att_iters}
        src_map = {iter_index_from_name(p): p for p in src_iters}
        for sp in sel_iters:
            idx = iter_index_from_name(sp)
            ap = att_map.get(idx)
            src = src_map.get(idx)
            sel_rows = read_csv_rows(sp)
            att_rows = read_csv_rows(ap) if ap else []
            src_rows = read_csv_rows(src) if src else []
            html_parts.append(f"<div class='iter'><h3>Iteration {idx:02d}</h3>")
            if sel_rows:
                html_parts.append(_table(["arg_id","status","priority","topic","action","source","role"], sel_rows))
            else:
                html_parts.append("<p class='muted'>No selection table.</p>")
            if att_rows:
                merged = _attach_reasons(att_rows, edge_reasons)
                html_parts.append(_table(["attacker","target","reason"], merged))
            else:
                html_parts.append("<p class='muted'>No attacks table.</p>")
            if src_rows:
                html_parts.append(_table(["source","role","total_args","accepted","rejected","acceptance_rate","attacks_out","attacks_in"], src_rows))
            else:
                html_parts.append("<p class='muted'>No source summary table.</p>")
            html_parts.append("</div>")
    else:
        html_parts.append("<p class='muted'>No iteration CSVs found.</p>")

    # --- NEW: Parameter sweep (aggregate) section ---
    html_parts.append("<h2>Parameter sweep (aggregate)</h2>")
    sweep_imgs = [
        run_dir/"drone_sweep_policy.png",
        run_dir/"drone_sweep_success.png",
        run_dir/"drone_sweep_touchdown_time.png",
        run_dir/"drone_sweep_success_vs_gust.png",
        run_dir/"drone_sweep_ttd_vs_vx.png",
        run_dir/"drone_sweep_policy_rate_vs_gust.png",
    ]
    sweep_csvs = [
        run_dir/"drone_sweep_results.csv",
        run_dir/"drone_sweep_agg.csv",
    ]

    have_sweep_img = False
    html_parts.append("<div class='plots'>")
    for im in sweep_imgs:
        if im.exists():
            have_sweep_img = True
            html_parts.append(f"<figure><img src='{escape(im.name)}'><figcaption>{escape(im.name)}</figcaption></figure>")
    html_parts.append("</div>")

    have_sweep_csv = any(c.exists() for c in sweep_csvs)
    if have_sweep_img or have_sweep_csv:
        html_parts.append("<p class='files'>")
        for c in sweep_csvs:
            if c.exists():
                html_parts.append(f"<a href='{escape(c.name)}'>{escape(c.name)}</a>")
        html_parts.append("</p>")
    else:
        html_parts.append("<p class='muted'>No sweep artifacts found. Generate with:<br>"
                          "<code>python tools/sweep_drone.py</code><br>"
                          "then: <code>python tools/sweep_aggregate.py</code></p>")

    return "\n".join(html_parts)


# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Summarize AF logs into an HTML report with per-iteration tables and embedded plots.")
    ap.add_argument("--run", required=True, help="Path to JSONL run (e.g., runs/isl_nano_run_*.jsonl)")
    ap.add_argument("--out", default="", help="Output HTML path (default: runs/af_summary.html)")
    args = ap.parse_args()

    jsonl = Path(args.run)
    run_dir = jsonl.parent
    run_name = jsonl.name

    events = read_jsonl(jsonl)
    accepted, _all_ge, diag_edges = collect_from_jsonl(events)
    edge_reasons = unique_edges(collect_attacks_from_events(events) + diag_edges)

    # Latest (final) CSVs; also collect iter CSVs for embedded sections
    sel_iters = list_iter_csvs(run_dir, "af_selection")
    att_iters = list_iter_csvs(run_dir, "af_attacks")
    src_iters = list_iter_csvs(run_dir, "af_sources")

    sel_path = sel_iters[-1] if sel_iters else (run_dir / "af_selection.csv")
    att_path = att_iters[-1] if att_iters else (run_dir / "af_attacks.csv")
    src_path = src_iters[-1] if src_iters else (run_dir / "af_sources.csv")

    final_selection_rows = read_csv_rows(sel_path)
    final_attacks_rows = read_csv_rows(att_path)
    final_source_rows = read_csv_rows(src_path)

    html_out = Path(args.out) if args.out else (run_dir / "af_summary.html")
    html_out.write_text(
        render_html(run_name, events, final_selection_rows, final_attacks_rows,
                    final_source_rows, sel_iters, att_iters, src_iters, edge_reasons, run_dir),
        encoding="utf-8"
    )
    print(f"Wrote: {html_out}")


if __name__ == "__main__":
    main()
