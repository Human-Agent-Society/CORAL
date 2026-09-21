"""Schedule export and yoked replay: hash-bound, checkpoint indices and counts only, and
the replay voids itself rather than replay an undefined exposure."""

from __future__ import annotations

from tests.evolution_fixtures import (  # noqa: F401
    CHECKPOINTED,
    FIVE,
    HI,
    OPEN,
    EvolutionStore,
    Harness,
    Path,
    _adaptive_run,
    _proposer,
    criteria,
    gmod,
    ground,
    json,
    proposal,
    pytest,
    reset,
    run_scored,
)


def test_exported_schedule_carries_timing_and_counts_and_nothing_else(h, monkeypatch):
    """A yoke that could read the adaptive run's criteria would not be blind."""
    store = _adaptive_run(h, monkeypatch)
    payload = store.export_publication_schedule("adaptive-run-1")
    assert payload["source_run"] == "adaptive-run-1"
    assert payload["schedule_kind"] == "checkpoint"
    # the scored-observation checkpoints, what each one did, and how many criteria: nothing else
    assert (
        len(payload["checkpoints"])
        == len(payload["accepted_counts"])
        == len(payload["statuses"])
        >= 1
    )
    assert any(payload["accepted_counts"])
    assert set(payload["statuses"]) <= {"published", "abstained", "blocked"}
    blob = json.dumps(payload)
    assert "Alpha" not in blob and "Beta" not in blob and "evidence" not in blob


def test_schedule_hash_rejects_an_edited_schedule(h, tmp_path, monkeypatch):
    store = _adaptive_run(h, monkeypatch)
    payload = store.export_publication_schedule("adaptive-run-1")
    sched = tmp_path / "sched.json"

    sched.write_text(json.dumps(payload))
    g = h.grader("y0", FIVE, {"mode": "yoked", "yoked_schedule_file": str(sched)})
    assert g._yoked_schedule()["source_run"] == "adaptive-run-1"

    payload["accepted_counts"][0] = 99
    sched.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        g._yoked_schedule()


def test_yoked_run_replays_the_exact_timing_and_counts(tmp_path, monkeypatch):
    src = Harness(root=tmp_path / "adaptive")
    store = _adaptive_run(src, monkeypatch)
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(store.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Blind1", "Blind2"))
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id=f"ag{i % 4}")

    ystore = EvolutionStore(yk.private)
    a_pubs = [(p["finalized_attempts"], p["accepted_count"]) for p in store.publications()]
    y_pubs = [(p["finalized_attempts"], p["accepted_count"]) for p in ystore.publications()]
    assert y_pubs == a_pubs, f"yoke did not match its twin: {y_pubs} vs {a_pubs}"

    # Identical exposure, different content — that is the whole contrast.
    a_names = {c.name for c in store.load_current().criteria}
    y_names = {c.name for c in ystore.load_current().criteria}
    assert len(a_names) == len(y_names) and a_names != y_names
    assert any(c.provenance == "trajectory_blind" for c in ystore.load_current().criteria)


def test_yoke_that_cannot_match_the_count_publishes_nothing_and_voids_the_pair(
    tmp_path, monkeypatch
):
    src = Harness(root=tmp_path / "adaptive")
    store = _adaptive_run(src, monkeypatch)
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(store.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")
    # One criterion where the replayed publication requires two.
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("OnlyOne"))
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")

    ystore = EvolutionStore(yk.private)
    assert ystore.load_current().version == 1, "an unmatched yoke must publish nothing"
    assert (yk.private / "evolving" / "replay_failures.jsonl").exists()


def test_yoked_record_logs_intended_and_delivered_index(tmp_path, monkeypatch):
    """Asynchronous grading can skip the intended attempt index entirely, so the
    replay fires at the first evaluation at or past it. Both numbers must be on
    the record: delivered exposure is what the analysis uses, and the slip is
    what the audit checks against the agreed tolerance."""
    src = Harness(root=tmp_path / "adaptive")
    store = _adaptive_run(src, monkeypatch)
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(store.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Blind1", "Blind2"))
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")

    pubs = EvolutionStore(yk.private).publications()
    assert pubs
    for p in pubs:
        assert "intended_scored" in p and "index_slip" in p
        assert p["index_slip"] == p["scored_attempts"] - p["intended_scored"]
        assert p["index_slip"] >= 0, "the replay must never fire early"


def test_checkpoint_schedule_export_and_yoked_replay(h, monkeypatch):
    """One checkpoint accepts, one abstains — the schedule must carry both
    outcomes, and the yoke must reproduce exactly that pattern."""

    def alpha_then_abstain(*, model, prompt, scratch_cwd, timeout=180):
        if "Alpha" not in alpha_then_abstain.seen:
            alpha_then_abstain.seen.add("Alpha")
            return {"new_criteria": ground(prompt, [proposal("Alpha")]), "notes": ""}
        return {"new_criteria": [], "notes": "nothing further observed"}

    alpha_then_abstain.seen = set()
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", alpha_then_abstain)
    for i in range(6):
        run_scored(h, f"a{i}", FIVE, HI, CHECKPOINTED, agent_id=f"ag{i % 2}")
    store = EvolutionStore(h.private)
    payload = store.export_publication_schedule("adaptive-run-1")
    assert payload["schedule_kind"] == "checkpoint"
    assert payload["checkpoints"] == [3, 5]
    assert payload["accepted_counts"] == [1, 0]
    blob = json.dumps(payload)
    assert "Alpha" not in blob, "the yoke must not be able to read the adaptive criteria"

    sched = h.root / "sched.json"
    sched.write_text(json.dumps(payload))
    reset()
    yk = Harness(root=h.root.parent / "yoked_ckpt")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Blind"))
    ycfg = {k: v for k, v in CHECKPOINTED.items() if k != "checkpoints"}
    ycfg = {**ycfg, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")
    ystore = EvolutionStore(yk.private)
    ypubs = ystore.publications()
    # the yoke must publish exactly at the checkpoint where adaptive accepted >0
    fired_indices = {p["checkpoint_index"] for p in ypubs}
    assert fired_indices == {0}
    assert ypubs[0]["accepted_count"] == 1
    assert ypubs[0]["accepted_criteria"][0]["cited_source_id"] == "brief"
    # the second checkpoint (adaptive abstained) must be recorded, not published
    all_decisions = [
        d for d in ystore.load_trigger_decisions() if d.get("checkpoint_index") is not None
    ]
    assert {d["checkpoint_index"] for d in all_decisions} == {0, 1}
    abstained = next(d for d in all_decisions if d["checkpoint_index"] == 1)
    assert abstained["published"] is False and abstained["accepted_count"] == 0


def test_checkpoint_yoke_records_zero_exposure_without_calling_the_proposer(h, monkeypatch):
    """When the adaptive arm abstained at a checkpoint, the yoke must record
    zero accepted criteria at that same checkpoint without ever invoking its
    own proposer -- calling it would only produce something that has to be
    filtered back out to preserve the matched count, at real API cost."""
    import hashlib

    calls = {"n": 0}

    def counting_abstain(*, model, prompt, scratch_cwd, timeout=180):
        calls["n"] += 1
        return {"new_criteria": [], "notes": ""}

    hashed = {
        "checkpoints": [2],
        "accepted_counts": [0],
        "statuses": ["abstained"],
        "complete": True,
    }
    sched = h.root / "sched.json"
    sched.write_text(
        json.dumps(
            {
                "source_run": "x",
                "schedule_kind": "checkpoint",
                "checkpoints": [2],
                "accepted_counts": [0],
                "statuses": ["abstained"],
                "complete": True,
                "schedule_sha256": hashlib.sha256(
                    json.dumps(hashed, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    )
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", counting_abstain)
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(3):
        run_scored(h, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")
    assert calls["n"] == 0, "the blind proposer must not be called for a zero-count checkpoint"
    store = EvolutionStore(h.private)
    decisions = [d for d in store.load_trigger_decisions() if d.get("checkpoint_index") is not None]
    assert len(decisions) == 1
    assert decisions[0]["accepted_count"] == 0 and decisions[0]["published"] is False


def test_checkpoint_schedule_hash_rejects_tampering(h, monkeypatch, tmp_path):
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    for i in range(4):
        run_scored(h, f"a{i}", FIVE, HI, CHECKPOINTED, agent_id=f"ag{i}")
    payload = EvolutionStore(h.private).export_publication_schedule("adaptive-run-1")
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(payload))
    g = h.grader("y0", FIVE, {"mode": "yoked", "yoked_schedule_file": str(sched)})
    assert g._yoked_schedule()["schedule_kind"] == "checkpoint"

    payload["accepted_counts"][0] = 99
    sched.write_text(json.dumps(payload))
    g2 = h.grader("y0b", FIVE, {"mode": "yoked", "yoked_schedule_file": str(sched)})
    with pytest.raises(ValueError, match="hash"):
        g2._yoked_schedule()


def test_blocked_checkpoint_is_not_exported_as_a_clean_abstention(h, monkeypatch):
    """A blocked checkpoint means the deadline passed before the proposer was
    ever invoked. Exporting it as accepted_count=0 would be indistinguishable
    from 'the proposer looked and found nothing' -- a different claim about
    the trajectory, and the yoke must not be allowed to replay it as one."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    cfg = {**OPEN, "checkpoints": [2], "latest_publication_attempt": 1}
    for i in range(3):
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    payload = store.export_publication_schedule("adaptive-run-1")
    assert payload["statuses"] == ["blocked"]
    assert payload["accepted_counts"] == [0]

    sched = h.root / "sched.json"
    sched.write_text(json.dumps(payload))
    g = h.grader("y0", FIVE, {"mode": "yoked", "yoked_schedule_file": str(sched)})
    with pytest.raises(ValueError, match="blocked"):
        g._yoked_schedule()


def test_incomplete_schedule_is_rejected_not_silently_short(h, monkeypatch):
    """A run stopped, or ended, before evaluating every configured checkpoint
    must not let its yoke quietly replay fewer updates than intended."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    cfg = {**OPEN, "checkpoints": [3, 5], "window": 2}
    for i in range(4):  # only enough scored observations to reach checkpoint 3, not 5
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    payload = store.export_publication_schedule("adaptive-run-1", expected_checkpoints=[3, 5])
    assert payload["complete"] is False
    assert payload["checkpoints"] == [3]

    sched = h.root / "sched.json"
    sched.write_text(json.dumps(payload))
    g = h.grader("y0", FIVE, {"mode": "yoked", "yoked_schedule_file": str(sched)})
    with pytest.raises(ValueError, match="incomplete"):
        g._yoked_schedule()

    # without an expectation to check against, completeness cannot be judged
    # from the log alone, so it must not be reported false by default
    payload2 = store.export_publication_schedule("adaptive-run-1")
    assert payload2["complete"] is True


def test_yoked_checkpoint_crash_is_blocked_and_voids_the_replay(h, monkeypatch):
    """Same fix, yoked side: a required (want > 0) checkpoint whose proposer
    crashes must be 'blocked', and still counted as a replay failure -- the
    pair is void for that checkpoint either way, but the record must not
    claim the blind proposer examined anything."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha"))
    cfg = {**OPEN, "checkpoints": [3], "window": 2}
    for i in range(4):
        run_scored(h, f"a{i}", FIVE, HI, cfg, agent_id=f"ag{i}")
    store = EvolutionStore(h.private)
    payload = store.export_publication_schedule("adaptive-run-1")
    assert payload["accepted_counts"] == [1]

    sched = h.root / "sched.json"
    sched.write_text(json.dumps(payload))
    reset()

    def crashes(*, model, prompt, scratch_cwd, timeout=180):
        raise gmod.prop.EvolutionAgentError("evolution agent timed out after 600s")

    yk = Harness(root=h.root.parent / "yoked_crash")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", crashes)
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(4):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")
    ystore = EvolutionStore(yk.private)
    assert not ystore.publications()
    d = [x for x in ystore.load_trigger_decisions() if x.get("checkpoint_index") is not None][0]
    assert d["status"] == "blocked"
    assert d["required_count"] == 1
    failures = json.loads(
        (Path(yk.private) / "evolving" / "replay_failures.jsonl").read_text().splitlines()[0]
    )
    assert "proposer invocation failed" in failures["reason"]
