from __future__ import annotations

import json

import pytest

from coral.hub.interventions import (
    RELATIVE_LOG,
    append_intervention_event,
    content_sha256,
    load_intervention_events,
)


def test_delivery_event_is_append_only_hashed_and_idempotent(tmp_path):
    event = {
        "agent_id": "captain-ahab",
        "attempt_id": "abc123",
        "channel": "heartbeat_resume",
        "prompt_source": "heartbeat:reflect",
        "action_names": ["reflect"],
        "rubric_version_scored": 2,
        "content": "exact evaluator feedback",
        "delivered_at": "2026-09-17T12:00:00+00:00",
    }
    first = append_intervention_event(tmp_path, event)
    second = append_intervention_event(tmp_path, event)

    rows = [json.loads(x) for x in (tmp_path / RELATIVE_LOG).read_text().splitlines()]
    assert rows == [first]
    assert second["event_id"] == first["event_id"]
    assert first["delivery_status"] == "dispatched_to_runtime"
    assert first["content_sha256"] == content_sha256(event["content"])
    assert first["content_chars"] == len(event["content"])
    assert load_intervention_events(tmp_path) == rows


@pytest.mark.parametrize("missing", ["agent_id", "channel", "content"])
def test_delivery_event_requires_an_auditable_payload(tmp_path, missing):
    event = {"agent_id": "a", "channel": "resume", "content": "x"}
    event.pop(missing)
    with pytest.raises(ValueError):
        append_intervention_event(tmp_path, event)


def test_repeated_delivery_without_caller_identity_stays_visible(tmp_path):
    """Two genuine insertions of the same payload are two events, not one."""
    event = {"agent_id": "a", "channel": "agent_context", "content": "same feedback"}
    first = append_intervention_event(tmp_path, event)
    second = append_intervention_event(tmp_path, event)
    rows = load_intervention_events(tmp_path)
    assert len(rows) == 2
    assert first["content_sha256"] == second["content_sha256"]
    assert first["event_id"] != second["event_id"]


def test_caller_cannot_forge_delivery_status_or_schema(tmp_path):
    stored = append_intervention_event(
        tmp_path,
        {
            "agent_id": "a",
            "channel": "agent_context",
            "content": "x",
            "delivery_status": "read_and_understood",
            "schema": 99,
        },
    )
    assert stored["delivery_status"] == "dispatched_to_runtime"
    assert stored["schema"] == 1


def test_every_manager_prompt_path_routes_through_one_recorder():
    """Recording lives in _setup_and_start_agent, so no call site can bypass it.

    If a new launch path is added that talks to a runtime directly, this test
    fails and the research ledger's 'delivery_unverified' label stays honest.
    """
    import inspect

    from coral.agent import manager

    source = inspect.getsource(manager.AgentManager)
    assert source.count("_record_prompt_dispatch(") == 2  # one def, one call
    start = inspect.getsource(manager.AgentManager._setup_and_start_agent)
    assert "_record_prompt_dispatch(" in start
    for name in ("_restart_agent", "_interrupt_and_resume"):
        assert "_record_prompt_dispatch(" not in inspect.getsource(
            getattr(manager.AgentManager, name)
        )
