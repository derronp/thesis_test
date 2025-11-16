import os, subprocess
from pathlib import Path

class DesktopActuators:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def write_file(self, path: str, content: str):
        p = self.workspace / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return str(p)

    def run_py(self, script_path: str, args=None, venv_python: str = None):
        args = args or []
        python_exe = venv_python or "python"
        cmd = [python_exe, script_path] + args
        res = subprocess.run(cmd, cwd=self.workspace, capture_output=True, text=True)
        return {"returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr, "cmd": cmd}

    def create_sample_html(self, path: str):
        html = """<!doctype html><html><head><title>Demo Page</title></head>
        <body><h1 id='head'>Hello ISL-NANO</h1><p>deterministic content</p></body></html>"""
        return self.write_file(path, html)
