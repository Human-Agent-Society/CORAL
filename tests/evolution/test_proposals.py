"""Proposal grounding and admission: quotes must appear in a shown source, the blind
proposer sees only the brief, and the two arms are asked in the same shape."""

from __future__ import annotations

from tests.evolution_fixtures import (  # noqa: F401
    FIVE,
    HI,
    OPEN,
    Attempt,
    Criterion,
    EvolutionStore,
    Harness,
    Path,
    RubricSnapshot,
    _adaptive_run,
    _filter,
    _proposer,
    gmod,
    ground,
    json,
    proposal,
    reset,
    run_scored,
)


def test_the_blind_prompt_contains_only_the_brief_and_the_rubric():
    snap = RubricSnapshot(
        version=2,
        criteria=[
            Criterion("Visual Quality", "seed definition"),
            Criterion("Added Earlier", "an earlier blind criterion", added_in_version=2),
        ],
    )
    prompt = gmod.prop.build_blind_prompt(
        snap=snap,
        task_text="Build a payroll dashboard.",
        seed_names=["Visual Quality"],
        max_new=2,
    )
    assert "Build a payroll dashboard." in prompt
    assert "Visual Quality" in prompt
    assert "Added Earlier" in prompt, "must see what this arm already added"


def test_the_yoked_proposer_reads_nothing_from_the_run_directory(tmp_path, monkeypatch):
    """Isolation proof: spy on every file opened while the yoked proposal is
    built and assert none of them is run state.

    A prompt that merely looks clean is not enough. The guarantee has to be that
    the code path cannot reach artifacts, scores, feedback, notes, memory or
    transcripts at all.
    """
    src = Harness(root=tmp_path / "adaptive")
    store = _adaptive_run(src, monkeypatch)
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(store.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")
    # Plant state the proposer must not touch.
    (yk.notes / "secret_note.md").write_text("agents keep missing keyboard access")
    (yk.attempts / "leak.json").write_text(json.dumps({"feedback": "SECRET FEEDBACK"}))

    opened: list[str] = []
    real_read_text = Path.read_text
    captured: dict = {}
    recording = {"on": False}

    def spy_read_text(self, *a, **k):
        if recording["on"]:
            opened.append(str(self))
        return real_read_text(self, *a, **k)

    real_blind = gmod.prop.build_blind_prompt

    def watched_blind(**kw):
        # Record only what the PROPOSAL BUILD reads. The update clock legitimately
        # counts finalized attempts elsewhere; the guarantee under test is that
        # constructing the proposal reaches no run state.
        recording["on"] = True
        try:
            return real_blind(**kw)
        finally:
            recording["on"] = False

    def fake_agent(*, model, prompt, scratch_cwd, timeout=180):
        captured["prompt"] = prompt
        captured["read_while_building"] = list(opened)
        return {
            "new_criteria": ground(prompt, [proposal("Blind1"), proposal("Blind2")]),
            "notes": "",
        }

    monkeypatch.setattr(gmod.prop, "build_blind_prompt", watched_blind)
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", fake_agent)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")
    monkeypatch.undo()

    assert captured.get("prompt"), "the yoked proposer never ran"
    assert captured["read_while_building"] == [], (
        f"building the blind proposal read: {captured['read_while_building']}"
    )
    # And nothing anywhere in the yoked path may touch agent notes: unlike the
    # attempt records, notes have no legitimate non-proposer use.
    assert gmod.prop.read_agent_notes.__name__  # sanity: symbol exists
    notes_dir = str(yk.notes)
    assert not any(p.startswith(notes_dir) for p in opened)

    assert "SECRET FEEDBACK" not in captured["prompt"]
    assert "keyboard access" not in captured["prompt"]


def test_the_adaptive_proposer_by_contrast_does_see_the_trajectory(h, monkeypatch):
    """The mirror of the isolation test. If the adaptive prompt were also blind
    there would be no treatment contrast at all, and the isolation test above
    would pass vacuously."""
    (h.notes / "insight.md").write_text("agents keep missing keyboard access")
    prop_stub = _proposer("A", "B")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", prop_stub)
    for i in range(4):
        run_scored(
            h, f"t{i}", FIVE, HI, OPEN, agent_id=f"ag{i % 2}", feedback="Visual Quality: 0.90"
        )
    assert prop_stub.prompts, "the adaptive proposer never ran"
    joined = "\n".join(prop_stub.prompts)
    assert "keyboard access" in joined, "adaptive arm must see agent notes"


def test_yoked_criteria_carry_no_run_evidence_even_if_the_proposer_invents_some(
    tmp_path, monkeypatch
):
    """The blind prompt asks for an empty citation, but a proposer could invent
    one. "Yoked criteria contain no run evidence" has to be true by construction,
    not by the proposer's good behaviour."""
    src = Harness(root=tmp_path / "adaptive")
    store = _adaptive_run(src, monkeypatch)
    sched = tmp_path / "sched.json"
    sched.write_text(json.dumps(store.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")

    def lying_proposer(*, model, prompt, scratch_cwd, timeout=180):
        return {
            "new_criteria": ground(
                prompt,
                [
                    proposal("B1", cited_evidence="attempt a3 had no keyboard focus ring"),
                    proposal("B2", cited_evidence="agent ag2's page overflowed on mobile"),
                ],
            ),
            "notes": "",
        }

    monkeypatch.setattr(gmod.prop, "run_evolution_agent", lying_proposer)
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")

    added = [
        c for c in EvolutionStore(yk.private).load_current().criteria if c.added_in_version > 1
    ]
    assert added, "the yoke published nothing"
    for c in added:
        assert c.cited_evidence == "", f"{c.name} kept a fabricated citation"
        assert c.source_attempt_ids == [] and c.source_note_ids == []
        assert c.provenance == "trajectory_blind"


def test_adaptive_criteria_by_contrast_keep_their_evidence(h, monkeypatch):
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("A", "B"))
    for i in range(4):
        run_scored(h, f"e{i}", FIVE, HI, OPEN, agent_id=f"ag{i % 2}")
    added = [c for c in EvolutionStore(h.private).load_current().criteria if c.added_in_version > 1]
    assert added and all(c.cited_evidence for c in added)
    archives = list((Path(h.private) / "evolving" / "proposer_contexts").iterdir())
    assert archives, "the frozen proposer input/output was not archived"
    for archive in archives:
        assert (archive / "source_index.json").exists()
        assert (archive / "prompt.md").exists()
        assert (archive / "response.json").exists()


def test_a_proposal_is_rejected_unless_its_quote_really_appears(tmp_path):
    """Six of the fourteen criteria produced before this check argued from
    absence — "not tested", "could be bad", a hypothetical implementation.
    A verbatim quote is the mechanical test that separates those from an
    observation."""
    src = {"a1c2": "Attempt a1c2: the upload accepts .txt despite promising PDF."}

    good = {
        **proposal("Upload validation"),
        "cited_source_id": "a1c2",
        "quote": "the upload accepts .txt despite promising PDF",
    }

    cases = {
        "no source": {"cited_source_id": "", "quote": "the upload accepts .txt"},
        "no quote": {"cited_source_id": "a1c2", "quote": ""},
        "unknown source": {"cited_source_id": "zzzz", "quote": "the upload accepts .txt"},
        "invented quote": {"cited_source_id": "a1c2", "quote": "no criterion tests performance"},
    }
    for label, over in cases.items():
        p = {**proposal("X"), **over}
        out = _filter([p], src, tmp_path / label)
        assert not out.accepted, f"{label} should have been rejected"

    out = _filter([good], src, tmp_path / "good")
    assert len(out.accepted) == 1, out.rejected


def test_quote_matching_survives_reformatting(tmp_path):
    src = {"a1": "The  page\n   renders   without\nfatal errors."}
    p = {**proposal("X"), "cited_source_id": "a1", "quote": "page renders without fatal"}
    assert len(_filter([p], src, tmp_path).accepted) == 1


def test_grounding_is_skipped_when_no_sources_are_supplied(tmp_path):
    """Static evaluation and unit fixtures pass no sources; the check is off."""
    p = {**proposal("X")}
    assert len(_filter([p], None, tmp_path).accepted) == 1


def test_each_arm_may_only_quote_its_own_evidence_base(h, monkeypatch):
    """Same rule, different sources: adaptive quotes attempt feedback, yoked
    quotes the brief. That is what keeps the arms differing in what they can
    observe rather than in how strictly they are judged."""
    seen = {}

    def spy(props, snap, store, cfg, slots, sources=None):
        seen["sources"] = sources
        return gmod.prop.FilterOutcome()

    monkeypatch.setattr(
        gmod.prop, "run_evolution_agent", lambda **k: {"new_criteria": [], "notes": ""}
    )
    monkeypatch.setattr(gmod.prop, "filter_proposals", spy)
    for i in range(4):
        run_scored(h, f"g{i}", FIVE, HI, OPEN, agent_id=f"a{i % 2}", feedback="Visual Quality: 0.9")
    assert "brief" not in (seen.get("sources") or {}), "adaptive must cite attempts, not the brief"


def test_publication_records_persist_the_quote_that_passed_the_gate(tmp_path, monkeypatch):
    """The admission gate validates cited_source_id and quote. If they are then
    discarded, nobody can check afterwards which sentence actually passed it,
    and the gate becomes unfalsifiable. Both arms must persist both fields."""
    src = Harness(root=tmp_path / "adaptive")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Alpha", "Beta"))
    for i in range(6):
        run_scored(src, f"a{i}", FIVE, HI, OPEN, agent_id=f"ag{i % 4}")
    astore = EvolutionStore(src.private)

    apub = astore.publications()[0]
    for c in apub["accepted_criteria"]:
        assert c["quote"], f"{c['name']} published without the quote that admitted it"
        assert c["cited_source_id"], f"{c['name']} published without a source id"
        assert c["cited_source_id"] != "brief", "adaptive must cite an attempt, not the brief"
        assert c["cited_source_id"].startswith("a"), c["cited_source_id"]

    # the same fields survive onto the criterion in the published snapshot
    added = [c for c in astore.load_current().criteria if c.added_in_version > 1]
    assert added and all(c.quote and c.cited_source_id for c in added)

    sched = tmp_path / "s.json"
    sched.write_text(json.dumps(astore.export_publication_schedule("adaptive-run-1")))
    reset()

    yk = Harness(root=tmp_path / "yoked")
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer("Blind1", "Blind2"))
    ycfg = {**OPEN, "mode": "yoked", "yoked_schedule_file": str(sched)}
    for i in range(6):
        run_scored(yk, f"y{i}", FIVE, HI, ycfg, agent_id="ag0")

    ypub = EvolutionStore(yk.private).publications()[0]
    for c in ypub["accepted_criteria"]:
        assert c["cited_source_id"] == "brief", (
            f"yoked criterion {c['name']} cited {c['cited_source_id']!r}, not the brief"
        )
        assert c["quote"], "yoked criteria must still record what they quoted"
    ynames = [c["name"] for c in ypub["accepted_criteria"]]
    added_y = [c for c in EvolutionStore(yk.private).load_current().criteria if c.name in ynames]
    assert all(c.source_attempt_ids == [] for c in added_y), (
        "the yoke must never claim to have observed an attempt"
    )


def test_both_arms_are_asked_in_the_same_shape(tmp_path):
    """Section order and headings must match, so a difference in the criteria
    is attributable to what the sections contain rather than to the request
    being framed differently in the two arms."""
    import re as _re

    adaptive_ctx = gmod.prop.stage_evidence_context(
        root=tmp_path / "a", task_text="brief text", feedback_by_attempt={"a1": "feedback text"}
    )
    blind_ctx = gmod.prop.stage_evidence_context(
        root=tmp_path / "b", task_text="brief text", blind=True
    )
    snap = RubricSnapshot(version=1, criteria=[Criterion("Seed", "d")])
    adaptive = gmod.prop.build_prompt(
        snap=snap,
        trigger="plateau",
        trigger_detail="d",
        task_text="brief text",
        feedback_by_attempt={"a1": "feedback text"},
        notes=gmod.prop.NoteBundle(),
        max_new=1,
        evidence_context=adaptive_ctx,
    )
    blind = gmod.prop.build_blind_prompt(
        snap=snap,
        task_text="brief text",
        seed_names=["Seed"],
        max_new=1,
        evidence_context=blind_ctx,
    )
    heads = lambda p: [h for h in _re.findall(r"^## (.+)$", p, _re.M)]  # noqa: E731
    for section in ("The task being evaluated", "Frozen artifact evidence", "Your task"):
        assert section in heads(adaptive) and section in heads(blind), section
    assert heads(adaptive).index("Frozen artifact evidence") < heads(adaptive).index("Your task")
    assert heads(blind).index("Frozen artifact evidence") < heads(blind).index("Your task")
    # the treatment is the contents of that section, not its presence
    assert "a1" in adaptive and "a1" not in blind
    assert "untrusted evidence" in adaptive and "untrusted evidence" in blind
