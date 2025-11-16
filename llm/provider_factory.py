# llm/provider_factory.py
from __future__ import annotations
import os
from typing import Any, Dict
from llm.config import load_llm_config

def make_provider():
    cfg = load_llm_config()
    provider = (cfg.get("provider") or "lmstudio_multistep").lower()
    if provider in ("lmstudio_multistep", "lmstudio"):
        from llm.providers.lmstudio_multistep import LMStudioMultistepProvider
        lm = cfg["lmstudio"]
        api_key = lm.get("api_key", os.environ.get(lm.get("api_key_env", "LM_STUDIO_API_KEY"), "lm-studio"))
        return LMStudioMultistepProvider(
            model=cfg["model"],
            base_url=lm.get("base_url", "http://127.0.0.1:1234/v1"),
            api_key=api_key,
            parameters=cfg.get("parameters", {})
        )
    # llm/provider_factory.py (add this branch)
    elif provider == "openai_multistep":
        from llm.providers.openai_multistep import OpenAIMultistepProvider
        return OpenAIMultistepProvider(cfg)

    else:
        raise ValueError(f"Unknown provider: {provider}")
