# llm/utils.py
import json, re

def _strip_control_chars(s: str) -> str:
    # keep \t \n \r; remove other C0 controls
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", s)

def _scan_balanced(s: str, start_idx: int) -> str:
    """Return a balanced JSON substring starting at { or [."""
    stack = []
    i = start_idx
    in_str = False
    esc = False
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    raise ValueError("Unbalanced JSON")
                top = stack.pop()
                if (top == "{" and ch != "}") or (top == "[" and ch != "]"):
                    raise ValueError("Mismatched JSON brackets")
                if not stack:
                    # include this closing bracket
                    return s[start_idx:i+1]
        i += 1
    raise ValueError("No balanced JSON found")

def extract_json_block(text: str):
    """
    Robustly extract first JSON value (object or array) from possibly noisy LLM output:
    - try whole text
    - try fenced ```json blocks
    - scan for first balanced {...} or [...]
    - sanitize control chars before json.loads
    """
    # 1) try raw
    try:
        return json.loads(_strip_control_chars(text))
    except Exception:
        pass

    # 2) fenced block first
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        inner = _strip_control_chars(m.group(1))
        try:
            return json.loads(inner)
        except Exception:
            text = inner  # fall through to scanner on inner

    # 3) scan for balanced braces/brackets
    for pat in [r"\{", r"\["]:
        m2 = re.search(pat, text)
        if m2:
            blob = _scan_balanced(text, m2.start())
            return json.loads(_strip_control_chars(blob))

    raise ValueError("No JSON object/array found in LLM output")



def normalize_to_arguments(obj):
    """
    Accept either:
      - {"arguments": [...]} → returns [...]
      - [...]                → returns [...]
    """
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and "arguments" in obj and isinstance(obj["arguments"], list):
        return obj["arguments"]
    raise ValueError("JSON did not contain an arguments list")
