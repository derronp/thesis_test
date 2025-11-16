import os, hashlib
from pathlib import Path

class DesktopSensors:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def file_exists(self, path: str) -> bool:
        return (self.workspace / path).exists()

    def sha256(self, path: str) -> str:
        p = self.workspace / path
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
