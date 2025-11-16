import os, subprocess, hashlib, json, re, time
from pathlib import Path

def file_exists(path: str, timeout_s: float, step_fn=None, dt: float = 0.1):
    t = 0.0
    while t <= timeout_s:
        if os.path.exists(path):
            return {"check":"file_exists","status":"PASS","elapsed_s":t,"path":path}
        if step_fn: step_fn(dt)
        t += dt
    return {"check":"file_exists","status":"FAIL","elapsed_s":t,"path":path}

def file_hash_equal(path: str, expected_sha256: str, timeout_s: float, step_fn=None, dt: float = 0.1):
    def sha256_file(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    t = 0.0
    while t <= timeout_s:
        if os.path.exists(path):
            digest = sha256_file(path)
            if digest == expected_sha256:
                return {"check":"file_hash_equal","status":"PASS","elapsed_s":t,"hash":digest,"path":path}
        if step_fn: step_fn(dt)
        t += dt
    return {"check":"file_hash_equal","status":"FAIL","elapsed_s":t,"path":path}

def proc_exitcode_ok(cmd: list, cwd: str = None, timeout_s: float = 120.0):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
        return {"check":"proc_exitcode_ok","status":"PASS" if res.returncode==0 else "FAIL",
                "returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr,
                "cmd": cmd, "cwd": cwd}
    except subprocess.TimeoutExpired:
        return {"check":"proc_exitcode_ok","status":"FAIL","error":"timeout","cmd":cmd,"cwd":cwd}

# --- Real-time control verifiers (add these) ---

def in_band(get_metric, target: float, tol: float, timeout_s: float, step_fn, dt: float):
    """
    Advance the simulation/plant with step_fn(dt) until either:
      - |metric - target| <= tol  -> PASS
      - elapsed time > timeout_s  -> FAIL
    Records metric history and elapsed time.
    """
    t = 0.0
    history = []
    while t <= timeout_s:
        val = float(get_metric())
        history.append(val)
        if abs(val - target) <= tol:
            return {"check": "in_band", "status": "PASS", "history": history, "elapsed_s": t}
        step_fn(dt)
        t += dt
    return {"check": "in_band", "status": "FAIL", "history": history, "elapsed_s": t}


def reach_threshold(get_metric, target: float, direction: str, timeout_s: float, step_fn, dt: float):
    """
    Like in_band, but checks one-sided threshold crossing:
      - direction == "down": metric <= target
      - direction == "up":   metric >= target
    """
    t = 0.0
    history = []
    while t <= timeout_s:
        val = float(get_metric())
        history.append(val)
        ok = (direction == "down" and val <= target) or (direction == "up" and val >= target)
        if ok:
            return {"check": "reach_threshold", "status": "PASS", "history": history, "elapsed_s": t}
        step_fn(dt)
        t += dt
    return {"check": "reach_threshold", "status": "FAIL", "history": history, "elapsed_s": t}

# --- Rich, deterministic verifiers ---

def stdout_contains(cmd: list, cwd: str = ".", must_include: str = "", timeout_s: float = 30.0):
    """Run a process and check that stdout contains a required substring."""
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
        ok = (res.returncode == 0) and (must_include in (res.stdout or ""))
        return {
            "check": "stdout_contains",
            "status": "PASS" if ok else "FAIL",
            "returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr,
            "must_include": must_include,
        }
    except Exception as e:
        return {"check": "stdout_contains", "status": "FAIL", "error": str(e)}

def stdout_regex(cmd: list, cwd: str = ".", pattern: str = "", timeout_s: float = 30.0):
    """Run a process and check stdout against a regex pattern."""
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
        ok = (res.returncode == 0) and re.search(pattern, res.stdout or "") is not None
        return {
            "check": "stdout_regex",
            "status": "PASS" if ok else "FAIL",
            "returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr,
            "pattern": pattern,
        }
    except Exception as e:
        return {"check": "stdout_regex", "status": "FAIL", "error": str(e)}

def json_field_equals(path: str, pointer: str, expected) -> dict:
    """
    Verify a JSON file has a field equal to expected.
    pointer: slash-separated keys (e.g., '/meta/version' or '/items/0/name')
    """
    p = Path(path)
    if not p.exists():
        return {"check": "json_field_equals", "status": "FAIL", "error": "file_missing", "path": path}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cur = data
        for tok in [t for t in pointer.split("/") if t]:
            if isinstance(cur, list):
                idx = int(tok)
                cur = cur[idx]
            else:
                cur = cur.get(tok)
        ok = (cur == expected)
        return {"check": "json_field_equals", "status": "PASS" if ok else "FAIL", "path": path, "pointer": pointer, "expected": expected, "actual": cur}
    except Exception as e:
        return {"check": "json_field_equals", "status": "FAIL", "error": str(e), "path": path}

def dir_contains(path: str, min_files: int = 1):
    p = Path(path)
    ok = p.exists() and p.is_dir() and sum(1 for _ in p.iterdir()) >= min_files
    return {"check": "dir_contains", "status": "PASS" if ok else "FAIL", "path": path, "min_files": min_files}

def file_glob_exists(root: str, pattern: str):
    rp = Path(root)
    ok = any(rp.glob(pattern))
    return {"check": "file_glob_exists", "status": "PASS" if ok else "FAIL", "root": root, "pattern": pattern}
