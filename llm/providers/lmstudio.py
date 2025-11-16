from openai import OpenAI
from llm.schema import LLMArgument
from llm.utils import extract_json_block, normalize_to_arguments
from pathlib import Path

PROMPT_PATH = "prompts/desktop_agentos.txt"

class LMStudioProvider:
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:1234/v1", api_key: str = "lm-studio"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def build_prompt(self, context: dict) -> str:
        goals = ", ".join(context.get("goals", []))
        hello = context["artifacts"]["hello_stdout"]
        search = context["artifacts"]["search_png"]
        with open(PROMPT_PATH, "r", encoding="utf-8") as fp:
            template = fp.read()
        # Avoid str.format(...) since the template contains JSON braces
        return (
            template
            .replace("{GOALS}", goals)
            .replace("{HELLO_PATH}", hello)
            .replace("{SEARCH_PATH}", search)
        )

    def generate_arguments(self, context):
        prompt = self.build_prompt(context)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role":"user","content":prompt}],
            temperature=0.0,
        )
        text = resp.choices[0].message.content
        # Debug
        Path("runs").mkdir(exist_ok=True, parents=True)
        Path("runs/_last_llm_agentos.txt").write_text(text, encoding="utf-8")

        data = extract_json_block(text)          # object OR array
        items = normalize_to_arguments(data)     # always a list now

        llm_args = []
        for item in items:
            llm_args.append(
                LLMArgument(
                    id=item["id"],
                    domain=item["domain"],
                    topic=item.get("topic", "desktop"),
                    pre=tuple(item.get("pre", [])),
                    action=item["action"],
                    effects=tuple(item.get("effects", [])),
                    verify=item["verify"],
                    priority=item.get("priority", 0),
                    deadline_ms=item.get("deadline_ms", 0),
                    source=item.get("source", "llm_planner"),
                    role=item.get("role", "planner"),
                )
            )
        return llm_args
