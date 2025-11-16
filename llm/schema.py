from dataclasses import dataclass
from typing import Tuple, Dict
@dataclass
class LLMArgument:
    id: str
    domain: str
    topic: str
    pre: Tuple[str, ...]
    action: Dict
    effects: Tuple[str, ...]
    verify: Dict
    priority: int = 0
    deadline_ms: int = 0
    source: str = "llm_planner"
    role: str = "planner"
def to_core(arg: "LLMArgument"):
    from core.arguments import Argument, ActionSpec, VerifySpec
    return Argument(
        id=arg.id, domain=arg.domain, topic=arg.topic, pre=arg.pre,
        action=ActionSpec(arg.action["name"], arg.action.get("params", {})),
        effects=arg.effects,
        verify=VerifySpec(arg.verify["name"], arg.verify.get("params", {})),
        priority=arg.priority, deadline_ms=arg.deadline_ms,
        source=arg.source, role=arg.role,
    )
