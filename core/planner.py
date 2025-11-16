from dataclasses import dataclass
from typing import Dict, Iterable, List
from .arguments import Argument

@dataclass
class PlanStep:
    arg_id: str
    priority: int
    deadline_ms: int

def order_plan(args: Dict[str, Argument], ids: Iterable[str]) -> List[PlanStep]:
    steps = [PlanStep(i, args[i].priority, args[i].deadline_ms) for i in ids if i in args]
    steps.sort(key=lambda s: (s.deadline_ms, -s.priority, s.arg_id))
    return steps
