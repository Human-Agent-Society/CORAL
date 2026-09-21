"""Integration tests for ``coral.grader.evolution``.

These target the interactions unit tests of isolated helpers cannot see:
concurrent evaluations across a version transition, version labelling,
finalization-gated observations, checkpoint gating, proposal filtering, and
failure accounting.
"""

from __future__ import annotations

import json
import random
import threading

import pytest

from coral.grader.evolution import policy as pol
from coral.grader.evolution import proposals as prop
from coral.grader.evolution.failures import FailureCode, classify_generic, inspect_evaluator_log
from coral.grader.evolution.grader import EvolvingTaskGrader
from coral.grader.evolution.state import (
    Criterion,
    EvolutionStore,
    Observation,
    RubricSnapshot,
)
from tests.evolution_harness import (
    BARRIERS,
    ENTERED,
    SCRIPT,
    SEQUENCE,
    Harness,
    HookedGrader,
    criteria,
    proposal,
    reset,
    run_scored,
)

ANCHORS = criteria(("Design", 3.0, True), ("Originality", 3.0, True))
FOUR = criteria(
    ("Design", 3.0, True),
    ("Originality", 3.0, True),
    ("Craft", 1.0, False),
    ("Function", 1.0, False),
)
#: A checkpoint at every scored observation from the second on: the first publication
#: happens on the grade that sees two finalized attempts.
FAST = {
    "mode": "adaptive",
    "window": 2,
    "checkpoints": list(range(2, 60)),
    "max_criteria": 4,
    "max_new_criteria_per_round": 2,
}
NEVER = {**FAST, "window": 999}
HI = {"Design": 0.9, "Originality": 0.9}


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


def _snap(crits, version=1):
    return RubricSnapshot(version=version, criteria=crits)


def _obs(n, version, scores, start=0):
    return [
        Observation(f"o{start + i}", version, sum(scores.values()) / len(scores), dict(scores))
        for i in range(n)
    ]


def test_concurrent_evaluations_across_a_version_transition_keep_their_own_version(h, monkeypatch):
    """B holds v1 while another attempt evolves the rubric; B must still be
    recorded under v1. The test asserts the transition actually happened, so it
    cannot pass vacuously if evolution silently fails."""
    h.proposals = [proposal("Accessibility")]
    h.install_agent_stub(monkeypatch)
    store = EvolutionStore(h.private)
    run_scored(h, "a1", ANCHORS, HI, FAST)  # one observation: gate still shut

    SCRIPT["b"] = {"scores": {"Design": 0.85, "Originality": 0.85}}
    BARRIERS["b"], ENTERED["b"] = threading.Event(), threading.Event()
    h.write_attempt("b")
    gb = h.grader("b", ANCHORS, FAST, agent_id="b")
    out: dict = {}
    t = threading.Thread(target=lambda: out.update(b=gb.evaluate()))
    t.start()
    assert ENTERED["b"].wait(timeout=5)
    v_start = store.current_version_number()

    run_scored(h, "a2", ANCHORS, HI, FAST)
    run_scored(h, "a3", ANCHORS, HI, FAST)
    assert store.current_version_number() == v_start + 1, (
        "test must actually cross a version boundary"
    )

    BARRIERS["b"].set()
    t.join(timeout=10)
    assert out["b"].metadata["rubric_version_scored"] == v_start
    ev = json.loads((store.events_dir / "b.json").read_text())
    assert ev["rubric_version_scored"] == v_start
    assert set(ev["criteria_in_force"]) == {c["name"] for c in ANCHORS}


def test_creating_attempt_reports_scored_and_created_versions_separately(h, monkeypatch):
    h.proposals = [proposal("Accessibility")]
    h.install_agent_stub(monkeypatch)
    store = EvolutionStore(h.private)
    run_scored(h, "x1", ANCHORS, HI, FAST)
    b2 = run_scored(h, "x2", ANCHORS, HI, FAST)
    b3 = run_scored(h, "x3", ANCHORS, HI, FAST)  # reconciles x1+x2 -> evolves -> scored under v2
    assert b2.metadata["rubric_version_scored"] == 1
    assert b3.metadata["rubric_version_scored"] == 2
    ev = json.loads((store.events_dir / "x2.json").read_text())
    assert ev["rubric_version_scored"] == 1
    assert ev["rubric_version_created_after"] == 2


def test_stale_result_never_carries_scores_for_newer_criteria(h, monkeypatch):
    h.proposals = [proposal("Accessibility")]
    h.install_agent_stub(monkeypatch)
    store = EvolutionStore(h.private)
    for aid in ("s1", "s2", "s3"):
        run_scored(h, aid, ANCHORS, HI, FAST)
    assert store.current_version_number() == 2
    only_v2 = {c.name for c in store.load_snapshot(2).criteria} - {
        c.name for c in store.load_snapshot(1).criteria
    }
    assert only_v2
    for o in store.observations(h.is_final):
        if o.rubric_version == 1:
            assert not set(o.scores) & only_v2


def test_every_score_traces_to_an_attempt_and_a_snapshot_containing_it(h):
    store = EvolutionStore(h.private)
    for aid in ("t1", "t2", "t3"):
        run_scored(h, aid, FOUR, {c["name"]: 0.5 for c in FOUR}, NEVER)
    obs = store.observations(h.is_final)
    assert obs
    for o in obs:
        snap = store.load_snapshot(o.rubric_version)
        assert snap is not None and all(snap.by_name(n) for n in o.scores)


def test_observations_are_a_pure_function_of_disk_state(h):
    """No cache, no applied-ids: the same disk state always yields the same
    observations, and nothing on disk needs repairing."""
    store = EvolutionStore(h.private)
    for i, aid in enumerate(("r1", "r2", "r3")):
        run_scored(h, aid, FOUR, {c["name"]: 0.4 + 0.1 * i for c in FOUR}, NEVER)
    a = [o.to_dict() for o in store.observations(h.is_final)]
    b = [o.to_dict() for o in store.observations(h.is_final)]
    assert a == b and len(a) == 3
    assert not (store.root / "observations.json").exists()
    assert not (store.root / "applied.json").exists()


def test_pending_attempt_is_not_an_observation(h):
    store = EvolutionStore(h.private)
    SCRIPT["p1"] = {"scores": HI}
    h.write_attempt("p1")
    h.grader("p1", ANCHORS, FAST).evaluate()
    assert (store.events_dir / "p1.json").exists()
    assert store.observations(h.is_final) == []


def test_finalizing_later_makes_it_an_observation_exactly_once(h):
    store = EvolutionStore(h.private)
    SCRIPT["p2"] = {"scores": HI}
    h.write_attempt("p2")
    h.grader("p2", ANCHORS, FAST).evaluate()
    h.finalize("p2")
    assert [o.attempt_id for o in store.observations(h.is_final)] == ["p2"]
    assert len(store.observations(h.is_final)) == 1  # repeated reads never double-count


def test_failed_events_are_retained_but_never_observations(h):
    store = EvolutionStore(h.private)
    SCRIPT["f1"] = {"fail": "boom"}
    h.write_attempt("f1")
    h.grader("f1", ANCHORS, {**FAST, "max_evaluation_retries": 0}).evaluate()
    h.finalize("f1", status="crashed")
    assert (store.events_dir / "f1.json").exists()
    assert store.observations(h.is_final) == []


def test_pending_attempts_never_influence_triggers(h, monkeypatch):
    h.proposals = [proposal("Accessibility")]
    h.install_agent_stub(monkeypatch)
    store = EvolutionStore(h.private)
    for aid in ("n1", "n2"):
        SCRIPT[aid] = {"scores": {"Design": 0.95, "Originality": 0.95}}
        h.write_attempt(aid)
        h.grader(aid, ANCHORS, FAST).evaluate()
    b = run_scored(h, "n3", ANCHORS, {"Design": 0.95, "Originality": 0.95}, FAST, finalize=False)
    assert b.metadata["rubric_version_scored"] == 1
    assert store.current_version_number() == 1 and h.agent_calls == []


def test_state_stays_valid_under_concurrent_writers(h):
    store = EvolutionStore(h.private)
    errors: list[Exception] = []

    def worker(i):
        try:
            run_scored(h, f"w{i}", FOUR, {c["name"]: 0.5 for c in FOUR}, NEVER)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=20)
    assert not errors
    assert len(store.observations(h.is_final)) == 6
    assert store.load_snapshot(1) is not None


# ===================================================== gate + triggers (11-16)


def test_a_note_that_exceeds_budget_is_skipped_not_fatal(h):
    import os

    cfg = pol.PolicyConfig(agent_notes_char_budget=900)
    for i, (name, body) in enumerate(
        [
            ("fat1.md", "a" * 400),
            ("fat2.md", "b" * 400),
            ("fat3.md", "c" * 400),
            ("tiny.md", "useful insight"),
        ]
    ):
        p = h.notes / name
        p.write_text(body)
        os.utime(p, (1_700_000_000 - i, 1_700_000_000 - i))
    b = prop.read_agent_notes(h.notes, cfg)
    assert any(s.endswith("fat3.md") for s, _ in b.skipped)
    assert any(s.endswith("tiny.md") for s in b.included) and "useful insight" in b.text


def test_note_provenance_reaches_the_changelog_and_the_criterion(h, monkeypatch):
    h.proposals = [proposal("Accessibility", source_note_ids=["n1"])]
    h.install_agent_stub(monkeypatch)
    (h.notes / "insight.md").write_text("agents keep missing keyboard access")
    store = EvolutionStore(h.private)
    for aid in ("g1", "g2", "g3"):
        run_scored(h, aid, ANCHORS, HI, FAST)
    assert "insight.md" in (store.root / "RUBRIC_CHANGELOG.md").read_text()
    snap = store.load_current()
    # Criteria enter active immediately: retirement is off, so probation would
    # be a label with no behaviour.
    new = [c for c in snap.criteria if c.added_in_version == snap.version]
    assert new and new[0].provenance == "agent_note" and new[0].source_note_ids == ["n1"]


def test_notes_disabled_includes_nothing(h):
    (h.notes / "x.md").write_text("something")
    b = prop.read_agent_notes(h.notes, pol.PolicyConfig(agent_notes_enabled=False))
    assert b.text == "" and b.included == []


def test_declared_fields_are_the_generalizability_filter(h):
    store = EvolutionStore(h.private)
    out = prop.filter_proposals(
        [
            proposal("Page-Specific Thing", generalizes=True),
            proposal("Declared Non-General", generalizes=False),
            proposal("Infeasible One", feasible=False),
            proposal("No Rationale", task_level=""),
            proposal("Keyboard Operability"),
        ],
        _snap([Criterion("Design", "d", anchor=True)]),
        store,
        pol.PolicyConfig(),
        free_slots=5,
    )
    assert [p.name for p in out.accepted] == ["Page-Specific Thing", "Keyboard Operability"]
    reasons = {p.name: r for p, r in out.rejected}
    assert "different solution strategies" in reasons["Declared Non-General"]
    assert "infeasible" in reasons["Infeasible One"]
    assert "task_level_rationale" in reasons["No Rationale"]


def test_adaptive_context_keeps_full_feedback_and_artifact_evidence(tmp_path):
    evidence = tmp_path / "persisted" / "attempt-1"
    (evidence / "artifact").mkdir(parents=True)
    (evidence / "screenshots").mkdir()
    artifact_text = "<main>reviewer cannot see the applicant essay before scoring</main>"
    (evidence / "artifact" / "index.html").write_text(artifact_text)
    (evidence / "screenshots" / "review.png").write_bytes(b"image")
    feedback = "first section\n" + ("x" * 2500) + "\n### Overall Critique\ndiagnostic tail"

    context = prop.stage_evidence_context(
        root=tmp_path / "context",
        task_text="Build the full portal brief.",
        feedback_by_attempt={"attempt-1": feedback},
        evidence_dirs_by_attempt={"attempt-1": evidence},
    )
    prompt = prop.build_prompt(
        snap=_snap([Criterion("Design", "d")]),
        trigger="plateau",
        trigger_detail="test",
        task_text="Build the full portal brief.",
        feedback_by_attempt={"attempt-1": feedback},
        notes=prop.NoteBundle(),
        max_new=1,
        evidence_context=context,
    )

    assert "diagnostic tail" in prompt, "feedback must not be sliced at 2,000 characters"
    source_id = "attempts/attempt-1/artifact_evidence/artifact/index.html"
    # Agent-authored source is staged and readable, but deliberately not
    # quotable: the agents write it while optimising against this rubric, so a
    # planted sentence must not be able to satisfy the admission gate.
    assert source_id in context.files
    assert (context.root / source_id).read_text() == artifact_text
    assert source_id not in context.sources
    assert source_id in context.readable_only
    assert context.sources["attempt-1"] == feedback, "evaluator feedback stays quotable"
    assert "attempts/attempt-1/artifact_evidence/screenshots/review.png" in context.files
    assert (context.root / "brief.txt").read_text() == "Build the full portal brief."
    assert "brief" not in context.sources, "adaptive criteria must cite trajectory evidence"


def test_yoked_context_contains_only_the_brief(tmp_path):
    context = prop.stage_evidence_context(
        root=tmp_path / "blind",
        task_text="Build a portal with accountless save and resume.",
        feedback_by_attempt={"leak": "a score that must not enter the control"},
        evidence_dirs_by_attempt={"leak": tmp_path},
        blind=True,
    )
    assert context.sources == {"brief": "Build a portal with accountless save and resume."}
    assert context.files == ["brief.txt"]


def test_retry_after_failure_records_exactly_one_observation(h):
    store = EvolutionStore(h.private)
    SEQUENCE["r"] = [
        {"fail": "Evaluator did not write evaluation.json"},
        {"scores": {"Design": 0.7, "Originality": 0.7}},
    ]
    h.write_attempt("r")
    b = h.grader("r", ANCHORS, {**FAST, "max_evaluation_retries": 1}).evaluate()
    h.finalize("r")
    assert b.aggregated is not None and b.metadata["evaluation_retries"] == 1
    assert len(store.observations(h.is_final)) == 1


def test_all_retries_failing_mutates_no_rubric_state(h):
    store = EvolutionStore(h.private)
    SEQUENCE["d"] = [{"fail": "x"}, {"fail": "x"}]
    h.write_attempt("d")
    b = h.grader("d", ANCHORS, {**FAST, "max_evaluation_retries": 1}).evaluate()
    h.finalize("d", status="crashed")
    assert b.aggregated is None and store.observations(h.is_final) == []
    ev = json.loads((store.events_dir / "d.json").read_text())
    assert ev["outcome"] == "failed" and ev["failure_summary"]


def test_session_limit_and_max_turns_stay_distinguishable(tmp_path):
    turn = tmp_path / "t.jsonl"
    turn.write_text(
        json.dumps({"type": "result", "subtype": "error_max_turns", "num_turns": 61}) + "\n"
    )
    lim = tmp_path / "l.jsonl"
    lim.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "You've hit your session limit"}]},
            }
        )
        + "\n"
        + json.dumps({"type": "result", "subtype": "success", "num_turns": 67})
        + "\n"
    )
    msg = "Evaluator did not write evaluation.json"
    assert classify_generic(msg, inspect_evaluator_log(turn)) is FailureCode.MAX_TURNS
    assert classify_generic(msg, inspect_evaluator_log(lim)) is FailureCode.ACCOUNT_SESSION_LIMIT
    assert (
        inspect_evaluator_log(lim)["terminal_subtype"] == "success"
    )  # exits "success" after writing nothing


def test_inner_grader_hook_refines_classification(h):
    store = EvolutionStore(h.private)
    SEQUENCE["hk"] = [{"fail": "could not use Playwright"}, {"fail": "could not use Playwright"}]
    h.write_attempt("hk")
    h.grader("hk", ANCHORS, {**FAST, "max_evaluation_retries": 1}, cls=HookedGrader).evaluate()
    ev = json.loads((store.events_dir / "hk.json").read_text())
    assert ev["failure_summary"] == {"playwright_unavailable": 2}
    # and without the hook the same message is merely unknown, not misfiled
    assert classify_generic("could not use Playwright") is FailureCode.UNKNOWN


def test_event_captures_model_snapshot_and_criteria_in_force(h):
    store = EvolutionStore(h.private)
    run_scored(h, "cap", ANCHORS, {"Design": 0.6, "Originality": 0.6}, FAST)
    ev = json.loads((store.events_dir / "cap.json").read_text())
    assert ev["evaluator_model"] == "stub" and ev["rubric_version_scored"] == 1
    assert ev["criteria_in_force"] == ["Design", "Originality"] and ev["agent_id"] == "a"


# ============================================================ generality + gate


def test_evolving_grader_requires_an_inner_grader_class():
    from coral.config import GraderConfig

    with pytest.raises(TypeError, match="inner_grader_cls"):
        EvolvingTaskGrader(GraderConfig(entrypoint="x:Y", timeout=1, args={}))


@pytest.mark.parametrize("seed", range(100))
def test_randomized_completion_order_keeps_state_consistent(tmp_path, seed):
    rng = random.Random(seed)
    h = Harness(tmp_path)
    store = EvolutionStore(h.private)
    ids = [f"z{i}" for i in range(6)]
    for aid in ids:
        SCRIPT[aid] = {"scores": {c["name"]: rng.uniform(0.3, 0.95) for c in FOUR}}
        BARRIERS[aid], ENTERED[aid] = threading.Event(), threading.Event()
        h.write_attempt(aid)
    threads = {
        aid: threading.Thread(target=h.grader(aid, FOUR, FAST, agent_id=aid[-1]).evaluate)
        for aid in ids
    }
    for t in threads.values():
        t.start()
    for aid in ids:
        assert ENTERED[aid].wait(timeout=10)
    order = ids[:]
    rng.shuffle(order)
    for aid in order:
        BARRIERS[aid].set()
        threads[aid].join(timeout=10)
        h.finalize(aid)
    obs = store.observations(h.is_final)
    assert len({o.attempt_id for o in obs}) == len(obs) == 6
    for o in obs:
        snap = store.load_snapshot(o.rubric_version)
        assert snap and all(snap.by_name(n) for n in o.scores)
    reset()


BANK = [{"name": f"Bank {i}", "description": f"bank criterion {i}, task-level"} for i in range(8)]
BANK_CFG = {**FAST, "proposal_source": "bank", "criteria_bank": BANK, "random_seed": 7}
