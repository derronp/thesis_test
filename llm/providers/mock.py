from typing import List, Dict
from llm.schema import LLMArgument

class MockProvider:
    def generate_arguments(self, context: Dict) -> List[LLMArgument]:
        target = float(context.get("target", 60.0))
        tol = float(context.get("tol", 0.5))
        timeout_s = float(context.get("timeout_s", 60.0))
        return [
            LLMArgument(
                id="L_sense_temp",
                domain="plant", topic="overtemp",
                pre=(), action={"name":"noop","params":{}},
                effects=("sensed:temp",), verify={"name":"file_exists","params":{"path":"__noop__", "timeout_s":0.0}},
                priority=30, deadline_ms=10
            ),
            LLMArgument(
                id="L_cool_to_band",
                domain="plant", topic="overtemp",
                pre=("sensed:temp",),
                action={"name":"cool_to_target","params":{"target":target}},
                effects=("state:cooling","goal:temp_in_band"),
                verify={"name":"in_band_rt","params":{"metric":"temp","target":target,"tol":tol,"timeout_s":timeout_s}},
                priority=25, deadline_ms=50
            )
        ]
