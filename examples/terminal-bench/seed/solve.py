"""Terminal-bench solver agent — wraps Terminus2 as a Harbor agent.

CORAL agents should improve this solver to achieve a higher pass rate.
"""

from terminus_2 import Terminus2


# LLM CONFIG - DO NOT CHANGE THIS!!!###
DEFAULT_MODEL = "anthropic/claude-opus-4-6"
DEFAULT_API_BASE = "https://api.anthropic.com/v1"
DEFAULT_API_KEY = "xxxx"
#######################################


class SolverAgent(Terminus2):
    """Terminus2 with hardcoded model defaults."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("model_name") is None:
            kwargs["model_name"] = DEFAULT_MODEL
        if kwargs.get("api_base") is None:
            kwargs["api_base"] = DEFAULT_API_BASE
        kwargs.setdefault("llm_kwargs", {})
        if "api_key" not in kwargs["llm_kwargs"]:
            kwargs["llm_kwargs"]["api_key"] = DEFAULT_API_KEY
        if kwargs.get("model_info") is None:
            kwargs["model_info"] = {
                "max_input_tokens": 160000,
                "max_output_tokens": 32768,
                "input_cost_per_token": 0.0,
                "output_cost_per_token": 0.0,
            }
        super().__init__(*args, **kwargs)
