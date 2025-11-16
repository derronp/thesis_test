
#!/usr/bin/env python3
import json
from pathlib import Path
import matplotlib.pyplot as plt

def main(traj_path="runs/drone_traj.json", out_path="runs/drone_traj.png"):
    p = Path(traj_path)
    if not p.exists():
        print("No trajectory found:", p); return
    data = json.loads(p.read_text(encoding="utf-8"))

    t = [d["t"] for d in data]
    x = [d["x"] for d in data]
    y = [d["y"] for d in data]
    vx = [d["vx"] for d in data]
    vy = [d["vy"] for d in data]

    # One plot per figure (per your matplotlib rules)
    plt.figure()
    plt.plot(x, y)
    plt.xlabel("x (m)")
    plt.ylabel("y (m)")
    plt.title("Drone Trajectory (x vs y)")
    plt.gca().invert_yaxis()  # ground at bottom visually
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print("Wrote:", out_path)

if __name__ == "__main__":
    main()
