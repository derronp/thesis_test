from typing import Set
from .arguments import ArgFramework
def grounded_extension(af: ArgFramework) -> Set[str]:
    attacked = {b for (a,b) in af.attacks}
    no_incoming = set(af.args.keys()) - attacked
    return no_incoming

def filter_attacks_by_priority(args, attacks):
    """Keep only attacks where attacker.priority >= target.priority."""
    out = set()
    for (attacker, target) in attacks:
        pa = getattr(args[attacker], "priority", 0)
        pt = getattr(args[target], "priority", 0)
        if pa >= pt:
            out.add((attacker, target))
    return out
