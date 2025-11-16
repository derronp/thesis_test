
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, Iterable, List
from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

# Topics: 'policy' and 'safety'
# Arguments: choose aggressive or conservative landing policy.
# Preconditions: none (both enabled).
# Verify: we'll evaluate after sim for touchdown zone & final speed constraints.

def generate_landing_AF(zone_radius: float=1.0, max_speed: float=0.6, max_time: float=20.0):
    args: Dict[str, Argument] = {}

    args["A_policy_aggr"] = Argument(
        id="A_policy_aggr",
        domain="drone",
        topic="policy",
        pre=tuple(),
        action=ActionSpec("set_policy", {"name": "aggressive"}),
        effects=("policy_set:aggressive",),
        verify=VerifySpec("after_sim_verify_all", {"zone_r": zone_radius, "max_speed": max_speed, "max_time": max_time}),
        priority=0,
        source="drone_policy",
        role="policy",
    )
    args["A_policy_cons"] = Argument(
        id="A_policy_cons",
        domain="drone",
        topic="policy",
        pre=tuple(),
        action=ActionSpec("set_policy", {"name": "conservative"}),
        effects=("policy_set:conservative",),
        verify=VerifySpec("after_sim_verify_all", {"zone_r": zone_radius, "max_speed": max_speed, "max_time": max_time}),
        priority=1,   # prefer safety when conflicts
        source="drone_policy",
        role="policy",
    )

    # Safety counter-arguments (symbolic): attack aggressive near-ground high descent
    attacks = {
        ("A_policy_cons", "A_policy_aggr"),   # safety prefers conservative over aggressive
    }
    return ArgFramework(args=args, attacks=attacks)
