# llm/config.py
from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Dict

_DEFAULT = {
    "provider": "lmstudio_multistep",  # default for Scenario 3
    "model": "qwen/qwen3-4b-2507",
    "parameters": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512},
    "lmstudio": {"base_url": "http://127.0.0.1:1234/v1", "api_key_env": "LM_STUDIO_API_KEY"},
    "openai":   {"base_url": None, "api_key_env": "OPENAI_API_KEY"}
}

def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

def load_llm_config() -> Dict[str, Any]:
    p = Path(os.environ.get("ISL_LLM_CONFIG", "configs/llm.json"))
    if not p.exists():
        return _DEFAULT
    with p.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)

    # Back-compat with your current llm.json (provider/model/base_url/api_key)
    cfg = dict(_DEFAULT)
    if "provider" in raw: cfg["provider"] = raw["provider"]
    if "model" in raw:    cfg["model"]    = raw["model"]

    # parameters (optional)
    if isinstance(raw.get("parameters"), dict):
        cfg["parameters"] = _merge(cfg["parameters"], raw["parameters"])

    # lmstudio block: accept legacy flat keys too
    lm = dict(cfg["lmstudio"])
    if "base_url" in raw: lm["base_url"] = raw["base_url"]
    if "api_key" in raw:  lm["api_key"]  = raw["api_key"]
    if isinstance(raw.get("lmstudio"), dict):
        lm = _merge(lm, raw["lmstudio"])
    cfg["lmstudio"] = lm

    # openai block (future)
    if isinstance(raw.get("openai"), dict):
        cfg["openai"] = _merge(cfg["openai"], raw["openai"])

    return cfg
