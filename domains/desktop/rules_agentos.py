from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

def generate_agentos_AF(goals: list, artifacts: dict):
    args = {}
    attacks = set()
    attacks_info = []

    if "ide_hello" in goals:
        args["A_run_ide_hello"] = Argument(
            id="A_run_ide_hello", domain="desktop", topic="agentos_demo",
            pre=(),
            action=ActionSpec("run_goal", {"goal": "ide hello"}),
            effects=("fs:hello_stdout exists",),
            # process exit-code checked at actuation; this is a simple OK placeholder
            verify=VerifySpec("proc_exitcode_ok", {"cmd": ["echo", "ok"]}),
            priority=20, deadline_ms=50, source="planner"
        )
        args["A_verify_ide_hello"] = Argument(
            id="A_verify_ide_hello", domain="desktop", topic="agentos_demo",
            pre=("fs:hello_stdout exists",),
            action=ActionSpec("noop", {}),
            effects=(),
            verify=VerifySpec("file_exists", {"path": artifacts["hello_stdout"], "timeout_s": 10.0}),
            priority=15, deadline_ms=60, source="planner"
        )
        attacks.add(("A_verify_ide_hello", "A_run_ide_hello"))
        attacks_info.append({
            "from": "A_verify_ide_hello",
            "to": "A_run_ide_hello",
            "reason": "Verification depends on hello artifact; do not interleave",
            "source": "planner"
        })

    if "web_search" in goals:
        args["A_run_web_search"] = Argument(
            id="A_run_web_search", domain="desktop", topic="agentos_demo",
            pre=(),
            action=ActionSpec("run_goal", {"goal": "search docs"}),
            effects=("fs:search_png exists",),
            verify=VerifySpec("proc_exitcode_ok", {"cmd": ["echo", "ok"]}),
            priority=20, deadline_ms=70, source="planner"
        )
        args["A_verify_web_search"] = Argument(
            id="A_verify_web_search", domain="desktop", topic="agentos_demo",
            pre=("fs:search_png exists",),
            action=ActionSpec("noop", {}),
            effects=(),
            verify=VerifySpec("file_exists", {"path": artifacts["search_png"], "timeout_s": 20.0}),
            priority=15, deadline_ms=80, source="planner"
        )
        attacks.add(("A_verify_web_search", "A_run_web_search"))
        attacks_info.append({
            "from": "A_verify_web_search",
            "to": "A_run_web_search",
            "reason": "Verification depends on search artifact; do not interleave",
            "source": "planner"
        })

    af = ArgFramework(args=args, attacks=attacks)
    af.attacks_info = attacks_info
    return af
