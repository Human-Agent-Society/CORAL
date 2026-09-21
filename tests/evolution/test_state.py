"""Attempt finalization, claims, events and the run manifest: the record is consistent
under concurrent graders and failures never masquerade as observations."""

from __future__ import annotations

from tests.evolution_fixtures import (  # noqa: F401
    FIVE,
    HI,
    OPEN,
    REPO,
    Criterion,
    EvolutionStore,
    Harness,
    Path,
    RubricSnapshot,
    ScoreBundle,
    _adaptive_run,
    _attempt,
    _event,
    _filter,
    _proposer,
    claim_attempt,
    finalize_attempt,
    gmod,
    ground,
    json,
    pol,
    proposal,
    pytest,
    read_attempt,
    reset,
    run_scored,
    write_attempt,
)


def test_finalization_is_monotonic(tmp_path):
    coral = tmp_path / ".coral"
    write_attempt(coral, _attempt("c1"))
    assert finalize_attempt(coral, _attempt("c1", "improved", 0.91, "real")) is True
    assert finalize_attempt(coral, _attempt("c1", "crashed", None, "boom")) is False
    kept = read_attempt(coral, "c1")
    assert kept.status == "improved" and kept.score == pytest.approx(0.91)


def test_claim_is_exclusive_per_attempt_and_non_blocking(tmp_path):
    coral = tmp_path / ".coral"
    with claim_attempt(coral, "c1") as first:
        assert first is True
        with claim_attempt(coral, "c1") as second:
            assert second is False
        with claim_attempt(coral, "c2") as other:
            assert other is True, "different attempts must still grade in parallel"
    with claim_attempt(coral, "c1") as again:
        assert again is True, "the claim must be released on exit"


def test_event_and_attempt_cannot_disagree(tmp_path):
    """Per-file first-write-wins is not enough: two graders can each win one
    file. One claim held across both writes is what makes them one grader."""
    coral = tmp_path / ".coral"
    store = EvolutionStore(tmp_path / "private")
    write_attempt(coral, _attempt("c1"))
    with claim_attempt(coral, "c1") as owned:
        assert owned
        store.write_event(_event("c1", 0.9, {"X": 0.9}))
        with claim_attempt(coral, "c1") as intruder:
            assert intruder is False
        finalize_attempt(coral, _attempt("c1", "improved", 0.9))
    assert store.load_events()[0]["aggregated"] == pytest.approx(0.9)
    assert read_attempt(coral, "c1").score == pytest.approx(0.9)


def test_a_retry_replaces_an_orphan_event_but_never_a_finalized_one(tmp_path):
    """A grader that wrote its event then died leaves an orphan: nothing was
    reported from it, so a retry may replace it. Once the attempt is finalized
    the event is history."""
    coral = tmp_path / ".coral"
    store = EvolutionStore(tmp_path / "private")

    def is_final(aid: str) -> bool:
        a = read_attempt(coral, aid)
        return a is not None and a.status != "pending"

    write_attempt(coral, _attempt("c1"))
    store.write_event(_event("c1", 0.9, {"X": 0.9}), is_finalized=is_final)
    store.write_event(_event("c1", 0.2, {"X": 0.2}), is_finalized=is_final)  # orphan -> replaced
    assert store.load_events()[0]["aggregated"] == pytest.approx(0.2)

    finalize_attempt(coral, _attempt("c1", "regressed", 0.2))
    store.write_event(_event("c1", 0.7, {"X": 0.7}), is_finalized=is_final)  # history -> refused
    assert store.load_events()[0]["aggregated"] == pytest.approx(0.2)


def test_publications_are_derived_from_the_diagnostics_not_stored_twice():
    """Two records of the same fact can disagree; one cannot."""
    src = (REPO / "coral" / "grader" / "evolution" / "state.py").read_text()
    assert "def publications" in src and 'd.get("published")' in src


def test_manifest_records_the_arm_and_does_not_drift_against_itself(h, monkeypatch, caplog):
    """`policy` round-trips through JSON, so comparing a tuple to a list would
    report drift on every call and train us to ignore a real warning."""
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("A", "B"))
    with caplog.at_level("ERROR"):
        for i in range(3):
            run_scored(h, f"m{i}", FIVE, HI, OPEN, agent_id="a")
    m = json.loads((Path(h.private) / "run_manifest.json").read_text())
    assert m["arm"] == "adaptive"
    assert m["policy"]["checkpoints"] == list(range(1, 60))
    assert m["policy"]["expansion_weight"] == pytest.approx(1.0)
    assert "drift" not in caplog.text


def test_eval_version_is_recorded_in_every_arm(tmp_path, monkeypatch):
    for mode in ("static", "adaptive"):
        reset()
        hh = Harness(root=tmp_path / mode)
        monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("A", "B"))
        b = run_scored(hh, "e0", FIVE, HI, {**OPEN, "mode": mode}, agent_id="a")
        assert b.metadata["eval_version"] == b.metadata["rubric_version_scored"] == 1


def test_static_arm_uses_the_same_retry_path_as_the_evolving_arms(h):
    """A static arm with no retry would lose attempts the other arms kept."""
    from tests.evolution_harness import SEQUENCE

    SEQUENCE["s0"] = [{"fail": "boom"}, {"scores": HI}]
    h.write_attempt("s0")
    b = h.grader("s0", FIVE, {"mode": "static", "max_evaluation_retries": 1}).evaluate()
    assert b.aggregated is not None, "the retry must have rescued the attempt"
    assert b.metadata["evaluation_retries"] == 1
    assert b.metadata["eval_version"] == 1


def test_publication_records_what_the_proposer_actually_spent(h, monkeypatch):
    """The arms share a resource ceiling but not realised computation: the
    adaptive proposer has an evidence tree to read. Recording turns and cost on
    the publication keeps that confound measurable instead of assumed away."""

    def metered(*, model, prompt, scratch_cwd, timeout=180):
        return {
            "new_criteria": ground(prompt, [proposal("Metered")]),
            "notes": "",
            "_coral_proposer_meta": {"num_turns": 7, "total_cost_usd": 0.42},
        }

    monkeypatch.setattr(gmod.prop, "run_evolution_agent", metered)
    for i in range(6):
        run_scored(h, f"m{i}", FIVE, HI, OPEN, agent_id=f"ag{i % 2}")
    pub = EvolutionStore(h.private).publications()[0]
    assert pub["proposer_compute"] == {"num_turns": 7, "total_cost_usd": 0.42}


def test_an_exhausted_usage_window_is_not_retried(h, monkeypatch):
    """A usage limit holds until the window resets, hours rather than seconds, so
    a retry cannot succeed and only consumes the quota the next attempt needs.
    Transient failures still get their retries."""
    calls = {"n": 0}

    def failing(criteria):
        calls["n"] += 1
        return ScoreBundle(
            scores={}, aggregated=None, feedback="Claude AI usage limit reached (rate limit)"
        )

    g = h.grader("cap0", FIVE, {**OPEN, "max_evaluation_retries": 3})
    monkeypatch.setattr(type(g), "_delegate", lambda self, c: failing(c))
    _, failures = g._evaluate_with_retries([], pol.PolicyConfig(max_evaluation_retries=3), "cap0")
    assert calls["n"] == 1, f"retried an exhausted window {calls['n']} times"
    assert failures[0].code.value == "account_session_limit"

    calls["n"] = 0

    def flaky(criteria):
        calls["n"] += 1
        return ScoreBundle(
            scores={}, aggregated=None, feedback="evaluator did not write evaluation.json"
        )

    g2 = h.grader("cap1", FIVE, {**OPEN, "max_evaluation_retries": 3})
    monkeypatch.setattr(type(g2), "_delegate", lambda self, c: flaky(c))
    g2._evaluate_with_retries([], pol.PolicyConfig(max_evaluation_retries=3), "cap1")
    assert calls["n"] == 4, "a non-capacity failure must still use its retries"


@pytest.mark.parametrize("mode", ["static", "adaptive", "yoked"])
def test_every_arm_masks_evaluator_failure_text_identically(mode):
    """An unattributed failure message ("the evaluator did not produce an output
    file") reads as "your change broke the grader" and drives agents to cosmetic
    edits. The message must say what actually happened, identically in every arm."""
    bundle = ScoreBundle(scores={}, aggregated=None, feedback="Evaluator did not write x")
    gmod.EvolvingTaskGrader._mask_infra_failure(bundle)
    assert bundle.feedback == gmod.INFRA_FAILURE_FEEDBACK
    assert "not evidence about the quality or complexity of your submission" in bundle.feedback
    assert "Do not modify your artifact" in bundle.feedback


def test_a_scored_attempt_keeps_its_real_feedback():
    """Only a *missing* score is an infrastructure failure. A low score is a
    result and must never be masked."""
    bundle = ScoreBundle(scores={}, aggregated=0.02, feedback="Fatal JS syntax error on line 1247")
    gmod.EvolvingTaskGrader._mask_infra_failure(bundle)
    assert bundle.feedback == "Fatal JS syntax error on line 1247"


def test_a_crashed_attempt_gets_no_reflection_prompt():
    """The 'decide: refine or pivot / what have you ruled out' framing invites
    the agent to explain a result that does not exist, leaving its own last
    change as the only available explanation."""
    from coral.agent.manager import AgentManager

    mgr = object.__new__(AgentManager)
    crashed = {
        "score": None,
        "status": "crashed",
        "commit_hash": "abc123def456",
        "title": "restructured the form",
        "feedback": gmod.INFRA_FAILURE_FEEDBACK,
    }
    prompt = mgr._build_score_prompt(crashed, 9)
    assert gmod.INFRA_FAILURE_FEEDBACK in prompt
    assert "This was an evaluator failure, not a result" in prompt
    assert "Do not revise the artifact" in prompt
    for reflection_cue in ("Keep working", "Run trial experiments", "refine or pivot", "Ablate"):
        assert reflection_cue not in prompt, f"reflection scaffolding leaked: {reflection_cue!r}"
