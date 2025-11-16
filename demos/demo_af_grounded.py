from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework
from core.af_solver import grounded_extension

def make_demo_af() -> ArgFramework:
    args = {
        "A_cool": Argument(
            id="A_cool",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("open_valve", {"valve": "V_cool", "u": 0.6}),
            effects=("d/dt temp < 0",),
            verify=VerifySpec("in_band", {"metric":"temp","target":70,"tol":0.5,"timeout_s":30}),
            priority=10,
            deadline_ms=200
        ),
        "A_wait": Argument(
            id="A_wait",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("noop", {}),
            effects=("d/dt temp ~ 0",),
            verify=VerifySpec("still_high", {"metric":"temp","threshold":75,"timeout_s":10}),
            priority=1,
            deadline_ms=200
        ),
        "A_heat": Argument(
            id="A_heat",
            domain="plant",
            topic="overtemp_alarm",
            pre=("temp > T_HIGH",),
            action=ActionSpec("set_heater_power", {"p": 1.0}),
            effects=("d/dt temp > 0",),
            verify=VerifySpec("in_band", {"metric":"temp","target":70,"tol":0.5,"timeout_s":30}),
            priority=0,
            deadline_ms=200
        ),
    }

    attacks = {
        ("A_cool", "A_wait"),
        ("A_cool", "A_heat"),
    }

    return ArgFramework(args=args, attacks=attacks)

if __name__ == "__main__":
    af = make_demo_af()
    ext = grounded_extension(af)
    print("Grounded extension:", sorted(ext))
    print("Chosen actions:", [af.args[a].action for a in sorted(ext)])
