from dataclasses import dataclass
from typing import Dict, Tuple, Set

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

@dataclass
class ArgFramework:
    args: Dict[str, Argument]
    attacks: Set[tuple]
