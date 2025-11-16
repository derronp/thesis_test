import json, time, csv

def _normalize_attacks(attacks):
    if not attacks:
        return []
    norm = []
    for edge in attacks:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            norm.append((edge[0], edge[1]))
    return norm

def summarize_sources(args, accepted_ids, attacks):
    """Build per-source contribution stats for AF exports."""
    acc = set(accepted_ids or [])
    summary = {}
    att_list = _normalize_attacks(attacks)

    for aid, arg in (args or {}).items():
        src = getattr(arg, "source", "unknown") or "unknown"
        role = getattr(arg, "role", "")
        key = (src, role)
        if key not in summary:
            summary[key] = {
                "source": src,
                "role": role,
                "total": 0,
                "accepted": 0,
                "attacks_out": 0,
                "attacks_in": 0,
            }
        entry = summary[key]
        entry["total"] += 1
        if aid in acc:
            entry["accepted"] += 1

    for attacker, target in att_list:
        arg_att = args.get(attacker) if args else None
        arg_tar = args.get(target) if args else None
        src_att = getattr(arg_att, "source", "unknown") if arg_att else "unknown"
        role_att = getattr(arg_att, "role", "") if arg_att else ""
        src_tar = getattr(arg_tar, "source", "unknown") if arg_tar else "unknown"
        role_tar = getattr(arg_tar, "role", "") if arg_tar else ""
        entry_att = summary.setdefault((src_att, role_att), {
            "source": src_att,
            "role": role_att,
            "total": 0,
            "accepted": 0,
            "attacks_out": 0,
            "attacks_in": 0,
        })
        entry_att["attacks_out"] += 1
        entry_tar = summary.setdefault((src_tar, role_tar), {
            "source": src_tar,
            "role": role_tar,
            "total": 0,
            "accepted": 0,
            "attacks_out": 0,
            "attacks_in": 0,
        })
        entry_tar["attacks_in"] += 1

    rows = []
    for key in sorted(summary.keys()):
        data = summary[key]
        total = data["total"]
        accepted = data["accepted"]
        rejected = max(total - accepted, 0)
        acc_rate = (accepted / total) if total else 0.0
        rows.append([
            data["source"],
            data["role"],
            total,
            accepted,
            rejected,
            f"{acc_rate:.2f}",
            data["attacks_out"],
            data["attacks_in"],
        ])
    return rows
def log_event(fp, kind: str, data: dict):
    fp.write(json.dumps({"ts": time.time(), "kind": kind, "data": data}) + "\n")
    fp.flush()

def export_csv(path, rows, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


# --- span + metrics helpers ---
import time
from contextlib import contextmanager

@contextmanager
def span(fp, name: str, extra: dict | None = None):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dt = time.perf_counter() - t0
        log_event(fp, "span", {"name": name, "elapsed_s": dt, **(extra or {})})

def log_metrics(fp, **kv):
    """
    Convenience: standardize per-run metrics. Examples:
    log_metrics(fp, status="PASS", steps_to_success=3, af_iters=2, time_to_fix_s=1.27)
    """
    log_event(fp, "metrics", kv)
