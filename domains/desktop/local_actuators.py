from pathlib import Path
import subprocess

class LocalDesktopActuators:
    def __init__(self, workspace: str = "workspace_desktop"):
        self.root = Path(workspace)
        self.root.mkdir(parents=True, exist_ok=True)

    def create_dir(self, relpath: str):
        p = (self.root / relpath).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(p)}

    def write_file(self, relpath: str, content: str):
        p = (self.root / relpath).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p)}

    def run_proc(self, cmd: list, cwd: str = ".", timeout_s: float = 120.0):
        workdir = (self.root / cwd).resolve()
        res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout_s)
        return {"returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr, "cwd": str(workdir)}
