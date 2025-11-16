from typing import List, Dict, Tuple
from llm.schema import LLMArgument
class MockDesktopProvider:
    def generate_arguments(self, context: Dict) -> List[LLMArgument]:
        goals: Tuple[str,...] = tuple(context.get("goals", ()))
        hello_path = context["artifacts"]["hello_stdout"]
        search_path = context["artifacts"]["search_png"]
        args: List[LLMArgument] = []
        if "ide_hello" in goals:
            args.append(LLMArgument(
                id="L_run_ide_hello", domain="desktop", topic="agentos_llm",
                pre=(), action={"name":"run_goal","params":{"goal":"ide hello"}},
                effects=("fs:hello_stdout exists",),
                verify={"name":"proc_exitcode_ok","params":{"cmd":["echo","ok"]}},
                priority=30, deadline_ms=40
            ))
            args.append(LLMArgument(
                id="L_verify_ide_hello", domain="desktop", topic="agentos_llm",
                pre=("fs:hello_stdout exists",),
                action={"name":"noop","params":{}},
                effects=(),
                verify={"name":"file_exists","params":{"path": hello_path, "timeout_s": 20.0}},
                priority=20, deadline_ms=50
            ))
        if "web_search" in goals:
            args.append(LLMArgument(
                id="L_run_web_search", domain="desktop", topic="agentos_llm",
                pre=(), action={"name":"run_goal","params":{"goal":"search docs"}},
                effects=("fs:search_png exists",),
                verify={"name":"proc_exitcode_ok","params":{"cmd":["echo","ok"]}},
                priority=30, deadline_ms=60
            ))
            args.append(LLMArgument(
                id="L_verify_web_search", domain="desktop", topic="agentos_llm",
                pre=("fs:search_png exists",),
                action={"name":"noop","params":{}},
                effects=(),
                verify={"name":"file_exists","params":{"path": search_path, "timeout_s": 30.0}},
                priority=20, deadline_ms=70
            ))
        return args
