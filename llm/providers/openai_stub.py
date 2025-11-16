from typing import List, Dict
from llm.schema import LLMArgument
class OpenAIProvider:
    def __init__(self, model: str):
        self.model = model
    def generate_arguments(self, context: Dict) -> List[LLMArgument]:
        from .mock import MockProvider
        return MockProvider().generate_arguments(context)
