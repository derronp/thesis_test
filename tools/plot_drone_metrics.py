
#!/usr/bin/env python3
"""
Plot drone metrics from runs/drone_traj.json.

Outputs (to runs/):
- drone_altitude_time.png        (y vs t)
- drone_vy_time.png              (vy vs t)
- drone_x_time.png               (x vs t)
- drone_speed_time.png           (||v|| vs t)

Rules: matplotlib only, one chart per figure, no custom colors.
"""
import json, math
from pathlib import Path
import matplotlib.pyplot as plt

def main(traj_path="runs/drone_traj.json", out_dir="runs"):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    p = Path(traj_path)
    if not p.exists():
        print("No trajectory found:", p); return
    data = json.loads(p.read_text(encoding="utf-8"))

    t  = [d["t"]  for d in data]
    x  = [d["x"]  for d in data]
    y  = [d["y"]  for d in data]
    vx = [d["vx"] for d in data]
    vy = [d["vy"] for d in data]
    spd = [math.hypot(vx[i], vy[i]) for i in range(len(t))]

    # Altitude vs time
    plt.figure()
    plt.plot(t, y)
    plt.xlabel("time (s)"); plt.ylabel("altitude y (m)"); plt.title("Altitude vs time")
    plt.gca().invert_yaxis()  # ground at bottom visually
    plt.savefig(out/"drone_altitude_time.png", dpi=150, bbox_inches="tight")

    # Vertical speed vs time
    plt.figure()
    plt.plot(t, vy)
    plt.xlabel("time (s)"); plt.ylabel("vertical speed vy (m/s)"); plt.title("Vertical speed vs time")
    plt.savefig(out/"drone_vy_time.png", dpi=150, bbox_inches="tight")

    # Horizontal position vs time
    plt.figure()
    plt.plot(t, x)
    plt.xlabel("time (s)"); plt.ylabel("horizontal position x (m)"); plt.title("Horizontal position vs time")
    plt.savefig(out/"drone_x_time.png", dpi=150, bbox_inches="tight")

    # Speed magnitude vs time
    plt.figure()
    plt.plot(t, spd)
    plt.xlabel("time (s)"); plt.ylabel("speed ||v|| (m/s)"); plt.title("Speed magnitude vs time")
    plt.savefig(out/"drone_speed_time.png", dpi=150, bbox_inches="tight")

    print("Wrote:", out/"drone_altitude_time.png")
    print("Wrote:", out/"drone_vy_time.png")
    print("Wrote:", out/"drone_x_time.png")
    print("Wrote:", out/"drone_speed_time.png")

if __name__ == "__main__":
    main()
