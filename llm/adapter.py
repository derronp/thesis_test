from typing import Dict, Tuple, List
from .schema import LLMArgument, to_core

class LLMAdapter:
    def __init__(self, provider):
        self.provider = provider

    def generate_arguments(self, context: Dict):
        # backward-compat: providers that only return args
        out = self.provider.generate_arguments(context)
        if isinstance(out, tuple) and len(out) == 2:
            llm_args, attacks = out
        else:
            llm_args, attacks = out, []

        core_args = [to_core(a) for a in llm_args]
        return core_args, attacks
