# llm/providers/openai_multistep.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Tuple
import os

from openai import OpenAI
from llm.schema import LLMArgument
from llm.utils import extract_json_block, normalize_to_arguments

# Reuse the same prompt format your multistep LM Studio flow expects
PROMPT_PATH = "prompts/desktop_multistep.txt"

class OpenAIMultistepProvider:
    """
    OpenAI multistep provider with the same interface/behavior as LMStudioMultistepProvider.
    Returns (llm_args, attacks) where:
      - llm_args: List[LLMArgument]
      - attacks : List[Tuple[str,str,str]]  # (from, to, reason)
    """
    def __init__(self, cfg: Dict[str, Any]):
        # Config layout expected by your loader:
        # cfg["model"], cfg["parameters"]{temperature, top_p, max_tokens}, cfg["openai"]{base_url, api_key_env, api_key?}
        self.model = cfg.get("model", "gpt-4o-mini")
        self.parameters = cfg.get("parameters", {}) or {}
        oa = cfg.get("openai", {}) or {}

        # Base URL: keep None for api.openai.com
        base_url = oa.get("base_url", None)

        # API key resolution: explicit > env-var > fail
        api_key = oa.get("api_key")
        if not api_key:
            api_key = os.environ.get(oa.get("api_key_env", "OPENAI_API_KEY"))

        if not api_key:
            raise RuntimeError("OpenAI API key not found. Set OPENAI_API_KEY or put openai.api_key in configs/llm.json")

        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def build_prompt(self, user_intent: str) -> str:
        template = Path(PROMPT_PATH).read_text(encoding="utf-8")
        # Avoid .format() to keep JSON braces intact in the template
        return template.replace("{USER_INTENT}", user_intent)

    def generate_arguments(self, context: Dict[str, Any]) -> Tuple[List[LLMArgument], List[Tuple[str,str,str]]]:
        user_intent = context.get("user_intent", "")
        prompt = self.build_prompt(user_intent)

        temperature = float(self.parameters.get("temperature", 0.0))
        top_p = float(self.parameters.get("top_p", 1.0))
        max_tokens = int(self.parameters.get("max_tokens", 512))

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content

        # Breadcrumb for debugging
        Path("runs").mkdir(parents=True, exist_ok=True)
        Path("runs/_last_llm_openai_multistep.txt").write_text(text or "", encoding="utf-8")

        data = extract_json_block(text or "")
        items = normalize_to_arguments(data)  # returns the arguments list if present, otherwise list itself

        llm_args: List[LLMArgument] = []
        for it in items:
            llm_args.append(
                LLMArgument(
                    id=it["id"],
                    domain=it["domain"],
                    topic=it.get("topic", "multistep"),
                    pre=tuple(it.get("pre", [])),
                    action=it["action"],
                    effects=tuple(it.get("effects", [])),
                    verify=it["verify"],
                    priority=it.get("priority", 0),
                    deadline_ms=it.get("deadline_ms", 0),
                    source="llm",
                )
            )

        attacks: List[Tuple[str, str, str]] = []
        if isinstance(data, dict) and isinstance(data.get("attacks"), list):
            for atk in data["attacks"]:
                if isinstance(atk, dict) and "from" in atk and "to" in atk:
                    attacks.append((atk["from"], atk["to"], atk.get("reason", ""), atk.get("source","llm")))
                elif isinstance(atk, (list, tuple)) and len(atk) >= 2:
                    attacks.append((atk[0], atk[1], "", "llm"))

        return llm_args, attacks
