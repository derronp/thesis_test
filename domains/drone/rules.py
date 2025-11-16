
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, Iterable, List
from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

# Topics: 'policy' and 'safety'
# Arguments: choose aggressive or conservative landing policy.
# Preconditions: none (both enabled).
# Verify: we'll evaluate after sim for touchdown zone & final speed constraints.

def generate_overtemp_AF(temp: float, T_HIGH: float, target: float, tol: float, timeout_s: float):
    """Generate arguments and attacks for an over-temperature alarm from current state."""
    if not (temp > T_HIGH):
        # no alarm → empty AF
        return ArgFramework(args={}, attacks=set())

    args = {
        "A_cool": Argument(
            id="A_cool",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("open_valve", {"valve": "V_cool", "u": 0.7}),
            effects=("d/dt temp < 0",),
            verify=VerifySpec("in_band", {"metric": "temp", "target": target, "tol": tol, "timeout_s": timeout_s}),
            priority=10,
            deadline_ms=200,
            source="policy",
        ),
        "A_wait": Argument(
            id="A_wait",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("noop", {}),
            effects=("d/dt temp ~ 0",),
            verify=VerifySpec("still_high", {"metric": "temp", "threshold": T_HIGH, "timeout_s": 10}),
            priority=1,
            deadline_ms=200,
            source="safety",
        ),
        "A_heat": Argument(
            id="A_heat",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("set_heater_power", {"p": 1.0}),
            effects=("d/dt temp > 0",),
            verify=VerifySpec("in_band", {"metric": "temp", "target": target, "tol": tol, "timeout_s": timeout_s}),
            priority=0,
            deadline_ms=200,
            source="policy",  # explicitly tag
        ),
    }

    attacks = {
        ("A_cool", "A_wait"),
        ("A_cool", "A_heat"),
        # NOTE: no attack back on A_cool → A_cool is unattacked under perfect conditions
    }
    af = ArgFramework(args=args, attacks=attacks)

    af.attacks_info = [
        {"from": "A_cool", "to": "A_wait", "reason": "Cooling action dominates passive waiting under alarm.", "source": "policy"},
        {"from": "A_cool", "to": "A_heat", "reason": "Heating conflicts with alarm resolution; cooling preferred.", "source": "policy"},
    ]
    return af
