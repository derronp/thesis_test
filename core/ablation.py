import os

def get_ablation() -> str:
    """
    Returns one of: 'none', 'no_af', 'no_diag', 'no_priority'
    """
    v = os.environ.get("ISL_ABLATION", "none").strip().lower()
    if v not in {"none", "no_af", "no_diag", "no_priority"}:
        return "none"
    return v

def is_no_af():         return get_ablation() == "no_af"
def is_no_diag():       return get_ablation() == "no_diag"
def is_no_priority():   return get_ablation() == "no_priority"
