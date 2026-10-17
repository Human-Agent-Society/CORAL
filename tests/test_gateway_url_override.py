# SPDX-License-Identifier: MIT
"""Tests for gateway URL override warnings and environment variable precedence."""

import logging
import pytest

from coral.agent.runtime import apply_gateway_override


def test_override_sets_variable_without_warning_when_not_previously_set(caplog: pytest.LogCaptureFixture) -> None:
    env: dict[str, str] = {}
    logger = logging.getLogger("coral.agent.test")

    with caplog.at_level(logging.WARNING):
        apply_gateway_override(env, "ANTHROPIC_BASE_URL", "http://127.0.0.1:8080", agent_id="agent-1", runtime_logger=logger)

    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"
    assert len(caplog.records) == 0


def test_override_emits_warning_when_inheriting_different_url(caplog: pytest.LogCaptureFixture) -> None:
    env: dict[str, str] = {"ANTHROPIC_BASE_URL": "https://custom-proxy.internal/v1"}
    logger = logging.getLogger("coral.agent.test")

    with caplog.at_level(logging.WARNING):
        apply_gateway_override(env, "ANTHROPIC_BASE_URL", "http://127.0.0.1:8080", agent_id="agent-2", runtime_logger=logger)

    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"
    assert len(caplog.records) == 1
    assert "Agent agent-2: overriding inherited ANTHROPIC_BASE_URL (https://custom-proxy.internal/v1) with gateway http://127.0.0.1:8080" in caplog.records[0].message


def test_override_silent_when_previous_url_is_identical(caplog: pytest.LogCaptureFixture) -> None:
    env: dict[str, str] = {"OPENAI_BASE_URL": "http://127.0.0.1:8080"}
    logger = logging.getLogger("coral.agent.test")

    with caplog.at_level(logging.WARNING):
        apply_gateway_override(env, "OPENAI_BASE_URL", "http://127.0.0.1:8080", agent_id="agent-3", runtime_logger=logger)

    assert env["OPENAI_BASE_URL"] == "http://127.0.0.1:8080"
    assert len(caplog.records) == 0


def test_override_noop_when_gateway_url_none(caplog: pytest.LogCaptureFixture) -> None:
    env: dict[str, str] = {"OPENAI_BASE_URL": "https://api.openai.com/v1"}
    logger = logging.getLogger("coral.agent.test")

    with caplog.at_level(logging.WARNING):
        apply_gateway_override(env, "OPENAI_BASE_URL", None, agent_id="agent-4", runtime_logger=logger)

    assert env["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
    assert len(caplog.records) == 0
