import json, time, csv
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
