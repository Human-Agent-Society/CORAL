"""Tests for generated LiteLLM gateway configuration."""

import yaml

from coral.gateway.config import generate_default_litellm_config


def test_minimax_routes_cover_models_regions_and_protocols(tmp_path):
    for model_id in ("MiniMax-M3", "MiniMax-M2.7"):
        config_path = tmp_path / f"{model_id}.yaml"
        generate_default_litellm_config(config_path, model_id)
        routes = yaml.safe_load(config_path.read_text())["model_list"]

        assert len(routes) == 4
        assert {route["model_name"] for route in routes} == {
            model_id,
            f"{model_id}-anthropic",
        }
        assert {
            route["litellm_params"]["api_base"]
            for route in routes
            if route["model_name"] == model_id
        } == {
            "https://api.minimax.io/v1",
            "https://api.minimaxi.com/v1",
        }
        assert {
            route["litellm_params"]["api_base"]
            for route in routes
            if route["model_name"] == f"{model_id}-anthropic"
        } == {
            "https://api.minimax.io/anthropic",
            "https://api.minimaxi.com/anthropic",
        }
        assert all(
            route["litellm_params"]["api_key"] == "os.environ/MINIMAX_API_KEY" for route in routes
        )
