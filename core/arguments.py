from dataclasses import dataclass
from typing import Dict, Tuple, Iterable, Set, List

@dataclass(frozen=True)
class ActionSpec:
    name: str
    params: dict

@dataclass(frozen=True)
class VerifySpec:
    name: str
    params: dict

@dataclass
class Argument:
    id: str
    domain: str
    topic: str
    pre: Tuple[str, ...]
    action: ActionSpec
    effects: Tuple[str, ...]
    verify: VerifySpec
    priority: int = 0
    deadline_ms: int = 0
    # NEW: which agent/source contributed this argument
    # e.g., "policy", "safety", "diagnosis", "planner", "llm"
    source: str = "rule"

@dataclass
class ArgFramework:
    args: Dict[str, Argument]
    attacks: Set[tuple]
