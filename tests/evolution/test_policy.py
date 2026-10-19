"""Checkpoint timing and status: the scored-observation clock, deadlines, abstention vs
blocked, and one explainable decision record per grade."""

from __future__ import annotations

from tests.evolution_fixtures import (  # noqa: F401
    CHECKPOINTED,
    FIVE,
    HI,
    OPEN,
    EvolutionStore,
    _proposer,
    criteria,
    gmod,
    pol,
    pytest,
    run_scored,
    write_attempt,
)


def test_every_evaluation_writes_one_explainable_decision_record(h, monkeypatch):
    """The record must explain why the evaluator did or did not change without
    reconstructing hidden state after the run."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("A", "B"))
    store = EvolutionStore(h.private)
    for i in range(4):
        run_scored(h, f"d{i}", FIVE, HI, OPEN, agent_id=f"a{i % 2}")

    decisions = store.load_trigger_decisions()
    assert len(decisions) == 4
    for d in decisions:
        assert d["mode"] == "adaptive"
        assert isinstance(d["finalized_attempts"], int)
        assert "gate_open" in d and "gate_blockers" in d
        assert d["policy"]["checkpoints"] and "window_attempt_ids" in d

    pubs = store.publications()
    assert pubs, "expected a publication with a checkpoint at every attempt"
    p = pubs[0]
    assert p["selected_trigger"].startswith("checkpoint_")
    assert p["accepted_count"] == 2
    assert p["triggering_agent"] is not None, "solutions-to-evaluator provenance missing"
    assert all(c["cited_evidence"] for c in p["accepted_criteria"]), "no evidence citation"


def test_a_publication_must_leave_attempts_to_be_exposed_to(h, monkeypatch):
    """A criterion published on the last attempt of a run counts as a delivered
    update while nothing is ever scored against it and no later commit can
    respond to it; the deadline refuses that."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("A", "B"))
    cfg = {**OPEN, "latest_publication_attempt": 4}
    store = EvolutionStore(h.private)
    for i in range(9):
        run_scored(h, f"x{i}", FIVE, HI, cfg, agent_id=f"a{i % 4}")

    pubs = store.publications()
    assert pubs, "the guard must not block every publication"
    for p in pubs:
        assert p["finalized_attempts"] <= 4, f"published too late at {p['finalized_attempts']}"
    late = [
        d
        for d in store.load_trigger_decisions()
        if d["finalized_attempts"] > 4 and not d["gate_open"]
    ]
    assert any("too late to publish" in b for d in late for b in d["gate_blockers"])


def test_checkpoint_fires_one_attempt_after_the_configured_scored_count(h, monkeypatch):
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    for i in range(3):
        run_scored(h, f"a{i}", FIVE, HI, CHECKPOINTED, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    assert not store.publications(), "must not fire before the first checkpoint is reached"
    assert all(d.get("published") is False for d in store.load_trigger_decisions())

    run_scored(h, "a3", FIVE, HI, CHECKPOINTED, agent_id="ag3")
    store = EvolutionStore(h.private)
    pubs = store.publications()
    assert len(pubs) == 1
    assert pubs[0]["checkpoint_index"] == 0
    assert pubs[0]["checkpoint_value"] == 3
    assert pubs[0]["accepted_criteria"][0]["name"] == "Alpha"


def test_checkpoint_abstention_is_recorded_and_does_not_refire(h, monkeypatch):
    """The proposer returning an empty list is a valid answer, not a failure —
    and the checkpoint must still be consumed so the next evaluation asks the
    *next* checkpoint, not the same one again."""

    def abstain(*, model, prompt, scratch_cwd, timeout=180):
        return {"new_criteria": [], "notes": "nothing consequential observed"}

    monkeypatch.setattr(gmod.prop, "run_evolution_agent", abstain)
    for i in range(4):
        run_scored(h, f"a{i}", FIVE, HI, CHECKPOINTED, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    assert not store.publications()
    decisions = [d for d in store.load_trigger_decisions() if d.get("checkpoint_index") is not None]
    assert len(decisions) == 1, "the checkpoint must be consumed exactly once, not re-asked"
    assert decisions[0]["checkpoint_index"] == 0
    assert store.checkpoints_evaluated("adaptive") == 1

    # further attempts must advance to the SECOND checkpoint, not re-ask the first
    run_scored(h, "a4", FIVE, HI, CHECKPOINTED, agent_id="ag0")
    run_scored(h, "a5", FIVE, HI, CHECKPOINTED, agent_id="ag1")
    store = EvolutionStore(h.private)
    decisions = [d for d in store.load_trigger_decisions() if d.get("checkpoint_index") is not None]
    assert {d["checkpoint_index"] for d in decisions} == {0, 1}


def test_a_checkpoint_fires_whatever_the_score_spread_looks_like(h, monkeypatch):
    """Timing is a constant of the protocol, not a property of the trajectory: a
    run whose scores are wildly spread still evaluates the rubric at its checkpoint."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    spread = [{n: v for n in HI} for v in (0.1, 0.95, 0.3, 0.05)]
    for i, sc in enumerate(spread):
        run_scored(h, f"a{i}", FIVE, sc, CHECKPOINTED, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    pubs = store.publications()
    assert pubs, "high-variance scores must not block a fixed checkpoint"
    assert pubs[0]["selected_trigger"] == "checkpoint_3"


def test_checkpoint_respects_the_publication_deadline_as_a_safety_bound(h, monkeypatch):
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    cfg = {**CHECKPOINTED, "checkpoints": [2], "latest_publication_attempt": 1}
    for i in range(3):
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    assert not store.publications()
    decisions = [d for d in store.load_trigger_decisions() if d.get("checkpoint_index") is not None]
    assert len(decisions) == 1
    assert any("too late to publish" in b for b in decisions[0]["gate_blockers"])


def test_a_failed_evaluation_is_not_an_observation_and_does_not_advance_a_checkpoint(
    h, monkeypatch
):
    """Checkpoints count scored observations. An attempt whose evaluation crashed
    consumed budget but produced no evidence; it must not bring the proposer's
    checkpoint forward, or infrastructure failures would eat the evidence window."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    cfg = {**OPEN, "checkpoints": [3], "window": 5}
    h.write_attempt("crash0", status="crashed")  # a real attempt, no observation
    run_scored(h, "a0", FIVE, HI, cfg, agent_id="ag0")
    run_scored(h, "a1", FIVE, HI, cfg, agent_id="ag1")
    run_scored(h, "a2", FIVE, HI, cfg, agent_id="ag2")
    store = EvolutionStore(h.private)
    assert not store.publications(), (
        "3 scored observations do not exist yet (1 crash + 2 scored before this grade)"
    )

    run_scored(h, "a3", FIVE, HI, cfg, agent_id="ag3")
    store = EvolutionStore(h.private)
    pubs = store.publications()
    assert pubs, "checkpoint 3 fires once 3 scored observations exist, whatever the crash count"
    assert pubs[0]["checkpoint_value"] == 3 and pubs[0]["scored_attempts"] == 3
    assert pubs[0]["finalized_attempts"] == 4, (
        "submissions and failures are still counted, separately"
    )
    assert len(pubs[0]["window_attempt_ids"]) == 3


@pytest.mark.parametrize(
    "bad,msg",
    [
        ([0, 5], "positive"),
        ([-1, 5], "positive"),
        ([5, 5], "unique"),
        ([5, 3], "increasing"),
    ],
)
def test_checkpoints_must_be_positive_unique_and_increasing(bad, msg):
    with pytest.raises(ValueError, match=msg):
        pol.PolicyConfig.from_args({"mode": "adaptive", "checkpoints": bad})


def test_a_crashed_proposer_is_blocked_not_abstained(h, monkeypatch):
    """A proposer call rejected by an exhausted account must not be recorded as
    'abstained': that would be indistinguishable from the proposer having looked
    at the evidence and found nothing. A proposer that never produced an answer
    is never recorded as having decided anything."""

    def crashes(*, model, prompt, scratch_cwd, timeout=180):
        raise gmod.prop.EvolutionAgentError(
            "evolution agent exited 1 [looks like a usage/rate limit rejection]: "
        )

    monkeypatch.setattr(gmod.prop, "run_evolution_agent", crashes)
    cfg = {**OPEN, "checkpoints": [3]}
    for i in range(4):
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    assert not store.publications()
    d = [x for x in store.load_trigger_decisions() if x.get("checkpoint_index") is not None][0]
    assert d["status"] == "blocked", "a proposer crash must not read as a content decision"
    assert "usage/rate limit" in d["gate_blockers"][0]
    assert d["accepted_count"] == 0

    # exported the same way a deadline-blocked checkpoint is: refused by the yoke loader
    payload = store.export_publication_schedule("adaptive-run-1")
    assert payload["statuses"] == ["blocked"]


def test_a_genuine_content_abstention_still_reads_as_abstained(h, monkeypatch):
    """The fix must not blur the other direction: a proposer that is
    successfully invoked and returns nothing is a real, valid finding."""

    def abstains(*, model, prompt, scratch_cwd, timeout=180):
        return {"new_criteria": [], "notes": "looked, nothing consequential"}

    monkeypatch.setattr(gmod.prop, "run_evolution_agent", abstains)
    cfg = {**OPEN, "checkpoints": [3]}
    for i in range(4):
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    d = [x for x in store.load_trigger_decisions() if x.get("checkpoint_index") is not None][0]
    assert d["status"] == "abstained"
    assert "gate_blockers" not in d or not d["gate_blockers"]
