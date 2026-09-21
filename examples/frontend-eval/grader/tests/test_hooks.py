"""AgenticEvaluator's optional hooks for coral.grader.evolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_evaluator.grader import AgenticEvaluator  # noqa: E402

from coral.config import GraderConfig  # noqa: E402
from coral.grader.evolution.failures import FailureCode  # noqa: E402
from coral.types import Score, ScoreBundle  # noqa: E402


def _g():
    g = AgenticEvaluator(GraderConfig(entrypoint="x:Y", timeout=1, args={}))
    g.private_dir = "/tmp/p"
    return g


def _fail(msg):
    return ScoreBundle(
        scores={"eval": Score(value=None, name="eval", explanation=msg)},
        aggregated=None,
        feedback=msg,
    )


def test_log_path_matches_where_the_evaluator_writes():
    assert _g().evaluator_log_path("abc").as_posix().endswith("/evaluator/abc/logs/evaluator.0.log")


def test_evolution_evidence_survives_scratch_and_codebase_cleanup(tmp_path):
    g = _g()
    g.private_dir = str(tmp_path / "private")
    codebase = tmp_path / "checkout"
    codebase.mkdir()
    (codebase / "index.html").write_text("<main>complete artifact tail</main>")
    (codebase / "node_modules").mkdir()
    (codebase / "node_modules" / "ignored.js").write_text("dependency")
    g.codebase_path = str(codebase)

    attempt_dir = tmp_path / "private" / "evaluator" / "abc"
    workspace = attempt_dir / "workspace"
    scratch = workspace / "scratch"
    scratch.mkdir(parents=True)
    # The evaluator is offered scratch/ but not held to it, and in the pilot it
    # wrote every screenshot into its cwd -- the workspace root -- so a
    # scratch-only scan captured nothing on all 26 attempts. Both must be found.
    (workspace / "01-desktop.png").write_bytes(b"png in cwd")
    (scratch / "02-mobile.png").write_bytes(b"png in scratch")
    # codebase/ is a symlink to the submitted checkout: the artifact's own
    # assets are not evaluation evidence, and following it escapes the workspace.
    (workspace / "codebase").symlink_to(codebase)
    (codebase / "logo.png").write_bytes(b"artifact asset, not evidence")
    data = {
        "criteria": [{"name": "Visual Quality", "score": 0.8, "rationale": "specific"}],
        "overall_critique": "the diagnostic synthesis survives in full",
    }
    evidence = g._persist_evolution_evidence(
        data=data, workspace_dir=workspace, attempt_dir=attempt_dir
    )

    assert g.evolution_evidence_dir("abc") == evidence
    assert json.loads((evidence / "evaluation" / "evaluation.json").read_text()) == data
    assert (evidence / "artifact" / "index.html").read_text().endswith("tail</main>")
    shots = sorted(p.name for p in (evidence / "screenshots").glob("*.png"))
    assert any("01-desktop" in s for s in shots), f"cwd screenshot was missed: {shots}"
    assert any("02-mobile" in s for s in shots), f"scratch screenshot was missed: {shots}"
    assert not any("logo" in s for s in shots), "followed the codebase symlink"
    assert not (evidence / "artifact" / "node_modules").exists()


def test_classify_maps_this_graders_own_messages():
    g = _g()
    assert (
        g.classify_failure(_fail("The evaluator reported it could not use Playwright"), {})
        is FailureCode.PLAYWRIGHT_UNAVAILABLE
    )
    assert (
        g.classify_failure(_fail("Evaluator did not write evaluation.json"), {})
        is FailureCode.INVALID_OUTPUT
    )
    assert (
        g.classify_failure(_fail("Evaluator output was not valid JSON: x"), {})
        is FailureCode.INVALID_OUTPUT
    )
    assert g.classify_failure(_fail("something else"), {}) is None  # defers to generic
