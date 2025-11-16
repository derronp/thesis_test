import subprocess
from pathlib import Path

class AgentOSActuators:
    def __init__(self, project_root: str, python_exe: str = None):
        self.project_root = Path(project_root)
        self.python_exe = python_exe or "python"

    def run_goal(self, goal: str, timeout_s: float = 180.0):
        cmd = [self.python_exe, "-m", "agent.main", "--goal", goal]
        res = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=timeout_s)
        return {"returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr, "cmd": cmd, "cwd": str(self.project_root)}
