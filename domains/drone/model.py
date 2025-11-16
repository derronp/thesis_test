
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Dict, Any, Callable

@dataclass
class DroneState:
    x: float = 0.0      # horizontal position (m)
    y: float = 20.0     # altitude (m, >0 means above ground)
    vx: float = 0.0     # horizontal velocity (m/s)
    vy: float = -0.1    # vertical velocity (m/s), negative = descending
    t: float = 0.0      # time (s)

@dataclass
class Wind:
    vx: float = 0.0     # constant wind horizontal (m/s)
    gust_amp: float = 0.0
    gust_period: float = 9999.0  # large = almost constant

class DroneSim:
    """Very small 2D landing simulator. Units in SI. Perfect conditions except wind.
    y=0 is ground. Touchdown occurs when y<=0.
    Control input u = (ax_cmd, ay_cmd) pseudo-accelerations from thrust/tilt [-2..+2 m/s^2].
    """
    def __init__(self, dt: float=0.05, max_time: float=20.0, wind: Wind|None=None):
        self.dt = dt
        self.max_time = max_time
        self.wind = wind or Wind(0.0, 0.0, 9999.0)

    def reset(self, state: DroneState|None=None) -> DroneState:
        self.s = state or DroneState()
        self.traj = [self._snap(self.s)]
        return self.s

    def _snap(self, s: DroneState) -> Dict[str, float]:
        return {"t": s.t, "x": s.x, "y": s.y, "vx": s.vx, "vy": s.vy}

    def step(self, ax_cmd: float, ay_cmd: float):
        dt = self.dt
        # saturate commands
        ax = max(-2.0, min(2.0, ax_cmd))
        ay = max(-2.0, min(2.0, ay_cmd))

        # wind model (simple sinusoidal gust on vx)
        wvx = self.wind.vx
        if self.wind.gust_amp > 0.0 and self.wind.gust_period > 1e-6:
            import math
            wvx += self.wind.gust_amp * math.sin(2.0*math.pi*(self.s.t/self.wind.gust_period))

        # integrate (semi-implicit Euler)
        self.s.vx += (ax + wvx*0.1) * dt
        self.s.vy += (ay) * dt  # ay counters gravity implicitly; perfect actuator
        self.s.x  += self.s.vx * dt
        self.s.y  += self.s.vy * dt
        self.s.t  += dt

        # clamp ground (inelastic touchdown: kill vertical speed; damp horizontal)
        if self.s.y <= 0.0:
            self.s.y = 0.0
            # simple landing model for perfect-conditions demo
            self.s.vy = 0.0
            self.s.vx *= 0.2  # light friction upon contact


        self.traj.append(self._snap(self.s))

    def run_policy(self, policy_fn: Callable[[DroneState], Tuple[float,float]]) -> Dict[str, Any]:
        """Run until touchdown or max_time."""
        self.traj = [self._snap(self.s)]
        while self.s.t < self.max_time and self.s.y > 0.0:
            ax, ay = policy_fn(self.s)
            self.step(ax, ay)
        return {"traj": self.traj, "touchdown_time": self.s.t, "final": self._snap(self.s)}

# Two simple policies
def policy_aggressive(s: DroneState) -> tuple[float, float]:
    # minimal horizontal correction (still tends to drift)
    ax = -0.1 * s.x - 0.2 * s.vx
    if s.y > 3.0:
        ay = -0.8
    elif s.vy < -0.5:
        ay = +0.9
    else:
        ay = +0.4
    return (ax, ay)



def policy_conservative(s: DroneState) -> tuple[float, float]:
    """
    Safer landing:
    - Horizontal PD to center over x=0 (counters wind drift).
    - Altitude PD + speed shaping, guaranteeing descent within time.
    """
    # Horizontal PD (toward x=0). Strong enough to keep within zone under default wind.
    ax = -0.8 * s.x - 1.2 * s.vx

    # Vertical target profile (slows as we approach ground)
    if s.y > 5.0:
        vy_tgt = -0.8
    elif s.y > 2.0:
        vy_tgt = -0.35
    elif s.y > 0.5:
        vy_tgt = -0.12
    else:
        vy_tgt = -0.05  # flare zone

    # Altitude PD term + speed shaping: ensures y → 0 before timeout
    # ay is saturated by the sim to [-2..+2], so larger gains are okay.
    ay = 0.6 * (0.0 - s.y) + 2.0 * (vy_tgt - s.vy)

    return (ax, ay)

