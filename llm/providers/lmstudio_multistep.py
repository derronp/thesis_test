# llm/lmstudio_multistep.py  (PATCH)
from openai import OpenAI
from pathlib import Path
from llm.schema import LLMArgument
from llm.utils import extract_json_block, normalize_to_arguments

PROMPT_PATH = "prompts/desktop_multistep.txt"

class LMStudioMultistepProvider:
    def __init__(self, model: str, base_url="http://127.0.0.1:1234/v1", api_key="lm-studio", parameters=None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.parameters = parameters or {}

    def build_prompt(self, user_intent: str) -> str:
        template = Path(PROMPT_PATH).read_text(encoding="utf-8")
        # Avoid .format() because JSON braces exist in template
        return template.replace("{USER_INTENT}", user_intent)

    def generate_arguments(self, context):
        # context expects: {"user_intent": "..."}
        prompt = self.build_prompt(context["user_intent"])

        # NEW: pull configurable generation params (with safe defaults for determinism)
        temperature = float(self.parameters.get("temperature", 0.0))
        top_p = float(self.parameters.get("top_p", 1.0))
        max_tokens = int(self.parameters.get("max_tokens", 512))

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role":"user","content":prompt}],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        ).choices[0].message.content

        # breadcrumb for debugging
        Path("runs").mkdir(parents=True, exist_ok=True)
        Path("runs/_last_llm_multistep.txt").write_text(resp, encoding="utf-8")

        data = extract_json_block(resp)
        items = normalize_to_arguments(data)  # returns the "arguments" list if present, else list itself

        # Collect arguments
        llm_args = []
        for it in items:
            llm_args.append(
                LLMArgument(
                    id=it["id"], domain=it["domain"], topic=it.get("topic","multistep"),
                    pre=tuple(it.get("pre", [])), action=it["action"], effects=tuple(it.get("effects", [])),
                    verify=it["verify"], priority=it.get("priority", 0), deadline_ms=it.get("deadline_ms", 0),source="llm",
                )
            )

        # Collect attacks if provided (support both pair-lists and dicts with reason)
        attacks = []
        if isinstance(data, dict) and isinstance(data.get("attacks"), list):
            for atk in data["attacks"]:
                if isinstance(atk, dict) and "from" in atk and "to" in atk:
                    attacks.append((atk["from"], atk["to"], atk.get("reason",""), atk.get("source","llm")))
                elif isinstance(atk, (list, tuple)) and len(atk) >= 2:
                    attacks.append((atk[0], atk[1], "", "llm"))

        return llm_args, attacks
