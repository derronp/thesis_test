from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

def generate_overpressure_AF(pressure: float, P_HIGH: float, target: float, timeout_s: float):
    if not (pressure > P_HIGH):
        return ArgFramework(args={}, attacks=set())

    args = {
        "A_relief": Argument(
            id="A_relief",
            domain="plant",
            topic="overpressure_alarm",
            pre=("pressure > P_HIGH",),
            action=ActionSpec("open_relief", {"u": 0.9}),
            effects=("d/dt pressure < 0",),
            verify=VerifySpec("in_band", {"metric":"pressure","target":target,"tol":0.05,"timeout_s":timeout_s}),
            priority=10,
            deadline_ms=200,
            source="plant_policy",
            role="policy",
        ),
        "A_reduce_inflow": Argument(
            id="A_reduce_inflow",
            domain="plant",
            topic="overpressure_alarm",
            pre=("pressure > P_HIGH",),
            action=ActionSpec("set_inflow", {"q": 0.1}),
            effects=("d/dt pressure < 0",),
            verify=VerifySpec("in_band", {"metric":"pressure","target":target,"tol":0.02,"timeout_s":timeout_s}),
            priority=8,
            deadline_ms=200,
            source="plant_policy",
            role="policy",
        ),
        "A_wait": Argument(
            id="A_wait",
            domain="plant",
            topic="overpressure_alarm",
            pre=("pressure > P_HIGH",),
            action=ActionSpec("noop", {}),
            effects=("d/dt pressure ~ 0",),
            verify=VerifySpec("still_high", {"metric":"pressure","threshold":P_HIGH,"timeout_s":10}),
            priority=1,
            deadline_ms=200,
            source="plant_policy",
            role="policy",
        ),
    }

    attacks = {
        ("A_relief","A_wait"),
        ("A_relief","A_reduce_inflow"),
        # relief is preferred under perfect conditions; keep it unattacked for grounded acceptance
    }
    return ArgFramework(args=args, attacks=attacks)
