"""Generate default LiteLLM configuration for CORAL gateway."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Map CORAL model shortnames to LiteLLM model identifiers
_MODEL_MAP: dict[str, list[dict]] = {
    "sonnet": [
        {
            "model_name": "sonnet",
            "litellm_params": {
                "model": "claude-sonnet-4-20250514",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
    ],
    "opus": [
        {
            "model_name": "opus",
            "litellm_params": {
                "model": "claude-opus-4-20250514",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
    ],
    "haiku": [
        {
            "model_name": "haiku",
            "litellm_params": {
                "model": "claude-haiku-4-20250514",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
    ],
    "gpt-5.4": [
        {
            "model_name": "gpt-5.4",
            "litellm_params": {
                "model": "gpt-5.4",
                "api_key": "os.environ/OPENAI_API_KEY",
            },
        },
    ],
    "openai/gpt-5": [
        {
            "model_name": "openai/gpt-5",
            "litellm_params": {
                "model": "gpt-5",
                "api_key": "os.environ/OPENAI_API_KEY",
            },
        },
    ],
}


def generate_default_litellm_config(path: Path, model: str = "sonnet") -> Path:
    """Write a starter litellm_config.yaml if one doesn't already exist.

    Returns the path to the config file.
    """
    if path.exists():
        logger.info(f"LiteLLM config already exists at {path}, skipping generation")
        return path

    model_list = _MODEL_MAP.get(model, _MODEL_MAP["sonnet"])

    config = {
        "model_list": model_list,
        "litellm_settings": {
            "drop_params": True,
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated default LiteLLM config at {path}")
    return path
