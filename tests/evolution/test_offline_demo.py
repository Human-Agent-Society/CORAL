"""The offline demo runs the complete evolution cycle without a model call.

Deterministic inner grader, scripted proposer (`evolution.proposer_command`),
real on-disk evolution store: seed rubric -> checkpoint -> grounded proposal ->
mechanical admission -> immutable v2 -> later attempts scored under v2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from coral.grader.evolution.state import EvolutionStore

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "evolving-rubric-demo"
sys.path.insert(0, str(DEMO / "grader" / "src"))

from tests.evolution_harness import Harness  # noqa: E402

pytest.importorskip("demo_grader")
from demo_grader.evolving import EvolvingDemoGrader  # noqa: E402

SEED = [
    {
        "name": "Has Title",
        "weight": 1.0,
        "description": "The note opens with a title. requires: # ",
    },
    {
        "name": "Names Sources",
        "weight": 1.0,
        "description": "The note names its sources. requires: sources",
    },
]
ADAPTIVE = {
    "mode": "adaptive",
    "checkpoints": [2],
    "max_criteria": 6,
    "max_new_criteria_per_round": 1,
    "window": 2,
    "proposer_command": ["python3", "{task_dir}/grader/src/demo_grader/scripted_proposer.py"],
}


def _grade(h: Harness, attempt_id: str, text: str, evolution: dict) -> dict:
    (h.root / "answer.md").write_text(text)
    h.write_attempt(attempt_id)
    g = h.grader(attempt_id, SEED, evolution, cls=EvolvingDemoGrader)
    g.codebase_path = str(h.root)
    bundle = g.evaluate()
    h.finalize(attempt_id, feedback=bundle.feedback)
    return {
        "version": bundle.metadata["rubric_version_scored"],
        "scores": {k: v.value for k, v in bundle.scores.items()},
        "feedback": bundle.feedback,
    }


def test_static_arm_never_changes_the_rubric(tmp_path):
    h = Harness(root=tmp_path)
    h.private  # creates the .coral layout
    (h.root / "coral" / "config_dir").write_text(str(DEMO))
    for i in range(4):
        out = _grade(h, f"s{i}", "# Title\n\nSources: none.\n", {"mode": "static"})
        assert out["version"] == 1 and set(out["scores"]) == {"Has Title", "Names Sources"}
    assert not (Path(h.private) / "evolving" / "versions").exists()


def test_adaptive_arm_publishes_a_grounded_criterion_at_the_checkpoint_and_scores_under_it(
    tmp_path,
):
    h = Harness(root=tmp_path)
    h.private  # creates the .coral layout
    (h.root / "coral" / "config_dir").write_text(str(DEMO))
    plain = "# Title\n\nSources: none. This note is about evaluation.\n"
    first = _grade(h, "a1", plain, ADAPTIVE)
    second = _grade(h, "a2", plain, ADAPTIVE)
    assert first["version"] == second["version"] == 1
    assert (
        "the artifact has no fenced code block" in second["feedback"]
    )  # the observation the proposer will quote

    # the third grade sees two finalized attempts: checkpoint 2 fires, the scripted
    # proposer quotes an observation from staged feedback, admission publishes v2
    third = _grade(h, "a3", plain, ADAPTIVE)
    store = EvolutionStore(h.private)
    assert third["version"] == 2 and store.current_version_number() == 2
    v2 = store.load_current()
    added = [c for c in v2.criteria if c.added_in_version == 2]
    assert [c.name for c in added] == ["Code Example"]
    c = added[0]
    assert c.quote == "the artifact has no fenced code block"
    assert c.cited_source_id.startswith("attempts/") and c.cited_source_id.endswith("feedback.md")
    assert c.provenance == "evaluator_feedback" and c.source_attempt_ids
    assert (
        third["scores"]["Code Example"] == 0.0
    )  # scored under v2, artifact still has no code block

    decisions = store.load_trigger_decisions()
    published = [d for d in decisions if d.get("published")]
    assert (
        len(published) == 1
        and published[0]["checkpoint_value"] == 2
        and published[0]["status"] == "published"
    )
    assert published[0]["accepted_count"] == 1
    assert (Path(h.private) / "evolving" / "RUBRIC_CHANGELOG.md").read_text().count(
        "## Version 2"
    ) == 1
    contexts = list((Path(h.private) / "evolving" / "proposer_contexts").glob("*"))
    assert contexts, "the exact evidence shown to the proposer is archived"

    # an agent that responds to the new criterion scores it; the version is unchanged (no more checkpoints)
    improved = plain + "\n```python\nprint('example')\n```\n"
    fourth = _grade(h, "a4", improved, ADAPTIVE)
    assert fourth["version"] == 2 and fourth["scores"]["Code Example"] == 1.0
    assert store.current_version_number() == 2
    # every event binds its scores to the version it was scored under
    for aid, want in (("a2", 1), ("a3", 2), ("a4", 2)):
        ev = json.loads((store.events_dir / f"{aid}.json").read_text())
        assert ev["rubric_version_scored"] == want


def test_legacy_trigger_keys_are_refused(tmp_path):
    from coral.grader.evolution.policy import PolicyConfig

    with pytest.raises(ValueError, match="removed protocol generation"):
        PolicyConfig.from_args({"mode": "adaptive", "checkpoints": [2], "warmup_attempts": 8})
    with pytest.raises(ValueError, match="checkpoints is empty"):
        PolicyConfig.from_args({"mode": "adaptive"})
