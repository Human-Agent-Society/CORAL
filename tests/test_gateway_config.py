"""Tests for generated LiteLLM gateway configuration."""

import json
from types import SimpleNamespace

import httpx
import pytest
import yaml

from coral.gateway.config import _MODEL_MAP, generate_default_litellm_config


@pytest.mark.parametrize("model_id", ["MiniMax-M3.1-Flash", "MiniMax-M3", "MiniMax-M2.7"])
@pytest.mark.parametrize("suffix", ["", "-anthropic"])
def test_minimax_routes_cover_models_regions_and_protocols(tmp_path, model_id, suffix):
    config_path = tmp_path / "litellm.yaml"
    generate_default_litellm_config(config_path, model_id + suffix)
    routes = yaml.safe_load(config_path.read_text())["model_list"]

    assert len(routes) == 4
    assert {route["model_name"] for route in routes} == {
        model_id,
        f"{model_id}-anthropic",
    }
    assert {
        route["litellm_params"]["api_base"] for route in routes if route["model_name"] == model_id
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


def test_current_minimax_catalog_is_flash_first():
    assert [model for model in _MODEL_MAP if model.startswith("MiniMax-")] == [
        "MiniMax-M3.1-Flash",
        "MiniMax-M3",
    ]


def test_existing_custom_config_is_not_rewritten(tmp_path):
    config_path = tmp_path / "litellm.yaml"
    original = "# User-owned routes\nmodel_list:\n  - model_name: custom-model\n"
    config_path.write_text(original)
    generate_default_litellm_config(config_path, "MiniMax-M3.1-Flash")
    assert config_path.read_text() == original


def test_non_minimax_default_is_unchanged(tmp_path):
    config_path = tmp_path / "litellm.yaml"
    generate_default_litellm_config(config_path)
    assert yaml.safe_load(config_path.read_text())["model_list"] == _MODEL_MAP["sonnet"]


@pytest.mark.parametrize("model_id", ["MiniMax-M3.1-Flash", "MiniMax-M3.1-Flash-anthropic"])
def test_manager_generates_selected_gateway_routes(tmp_path, monkeypatch, model_id):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from coral.agent.manager import AgentManager
    from coral.gateway.server import GatewayManager

    started = []
    monkeypatch.setattr(GatewayManager, "start", lambda gateway: started.append(gateway))
    manager = AgentManager.__new__(AgentManager)
    manager.paths = SimpleNamespace(run_dir=tmp_path, coral_dir=tmp_path / ".coral")
    manager.config = SimpleNamespace(
        agents=SimpleNamespace(
            model=model_id,
            gateway=SimpleNamespace(enabled=True, config="", port=4000, api_key="test-key"),
        )
    )
    manager._start_gateway_if_enabled()

    assert len(started) == 1
    routes = yaml.safe_load((tmp_path / "litellm_config.yaml").read_text())["model_list"]
    assert model_id in {route["model_name"] for route in routes}
    assert all("MiniMax-M3.1-Flash" in route["litellm_params"]["model"] for route in routes)


@pytest.mark.parametrize(
    "model_id,effort,saved",
    [
        ("MiniMax-M3.1-Flash", effort, False)
        for effort in (None, "low", "medium", "high", "xhigh", "max")
    ]
    + [
        ("MiniMax-M3", None, False),
        ("MiniMax-M2.7", None, False),
        ("MiniMax-M3.1-Flash", None, True),
        ("MiniMax-M2.7", None, True),
    ],
)
@pytest.mark.parametrize("route_index", range(4))
@pytest.mark.asyncio(loop_scope="module")
async def test_generated_routes_reach_real_litellm_http_transport(
    tmp_path, monkeypatch, model_id, effort, saved, route_index
):
    # Import only after disabling LiteLLM's remote cost-map refresh. All inference
    # requests use dummy credentials and stop at the serialized HTTP boundary.
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    import litellm

    monkeypatch.setattr(litellm, "telemetry", False)
    config_path = tmp_path / "litellm.yaml"
    generate_default_litellm_config(config_path, model_id)
    config = yaml.safe_load(config_path.read_text())
    route = config["model_list"][route_index]
    anthropic = route["model_name"].endswith("-anthropic")
    if saved:
        route["model_name"] = "saved-custom-alias"
        route["litellm_params"]["api_base"] = "https://gateway.example/" + (
            "anthropic" if anthropic else "v1"
        )
        config["model_list"] = [route]
        original = yaml.safe_dump(config)
        config_path.write_text(original)
        generate_default_litellm_config(config_path, "MiniMax-M3.1-Flash")
        assert config_path.read_text() == original
        route = yaml.safe_load(config_path.read_text())["model_list"][0]
    captured = []

    def send(client, request, **kwargs):
        captured.append(request)
        if anthropic:
            response = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": model_id,
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        else:
            response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return httpx.Response(200, json=response, request=request)

    async def send_async(client, request, **kwargs):
        return send(client, request, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", send_async)
    extra_body = {}
    if effort:
        extra_body["thinking"] = {"type": "adaptive"}
        if anthropic:
            extra_body["output_config"] = {"effort": effort}
        else:
            extra_body["reasoning_effort"] = effort
    image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6bH8AAAAASUVORK5CYII="
    messages = [{"role": "user", "content": "Hello"}]
    if effort:
        image_block = (
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image},
            }
            if anthropic
            else {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
        )
        messages[0]["content"] = [{"type": "text", "text": "Hello"}, image_block]
    router = litellm.Router(model_list=[route], num_retries=0)
    try:
        if anthropic:
            # The proxy's /v1/messages route uses this native API. Sending these
            # options through chat/completions would drop Anthropic-only fields.
            response = await router.aanthropic_messages(
                model=route["model_name"], messages=messages, max_tokens=4096, **extra_body
            )
            if hasattr(response, "model_dump"):
                response = response.model_dump()
            assert response["content"][0]["text"] == "OK"
        else:
            response = await router.acompletion(
                model=route["model_name"],
                messages=messages,
                max_tokens=4096,
                extra_body=extra_body,
                drop_params=config["litellm_settings"]["drop_params"],
            )
            assert response.choices[0].message.content == "OK"
    finally:
        router.reset()

    assert len(captured) == 1
    request = captured[0]
    suffix = "/v1/messages" if anthropic else "/chat/completions"
    assert str(request.url) == route["litellm_params"]["api_base"] + suffix
    body = json.loads(request.content)
    assert body["model"] == model_id
    assert body["max_tokens"] == 4096
    assert "Hello" in json.dumps(body["messages"])
    if effort:
        assert body["thinking"] == {"type": "adaptive"}
        if anthropic:
            assert body["output_config"] == {"effort": effort}
            assert "reasoning_effort" not in body
        else:
            assert body["reasoning_effort"] == effort
            assert "output_config" not in body
        assert image in json.dumps(body["messages"])
    else:
        assert "thinking" not in body
        assert "reasoning_effort" not in body
        assert "output_config" not in body
    assert "service_tier" not in body
    assert body.get("reasoning_split") is not False
