"""Frontier-Smith algorithmic grader.

Delegates evaluation to the ``frontier_cs`` package's ``SingleEvaluator``,
which compiles the agent's C++ solution, runs it against the problem's
test cases inside the go-judge sandbox, and reports a 0-100 score.

The 10 Frontier-Smith problems (``frontiersmith_1`` .. ``frontiersmith_10``)
live in the FrontierSmith repository under
``Frontier-CS/algorithmic/problems/``. The judge server resolves a
``problem_id`` against its ``PROBLEMS_DIR``; point that env var at the
FrontierSmith problems directory before starting the judge (see the README
in ``examples/frontier_smith/``) and pass the matching ``problem_id`` via
``grader.args`` in each task's ``task.yaml``.

``frontier_cs.SingleEvaluator`` insists on a ``base_dir`` that contains an
``algorithmic/`` directory; it normally auto-detects this from its own
install path, but that fails when the package is installed into a venv
(``site-packages/frontier_cs`` has no ``algorithmic/`` sibling). Set
``FRONTIER_CS_BASE_DIR`` to your local Frontier-CS clone (the same one
running ``docker compose``) so the evaluator skips auto-detection. The
directory's only role here is satisfying the validator and locating the
docker-compose file if the judge needs (re)starting; submissions go over
HTTP to ``judge_url``.
"""

from __future__ import annotations

import os
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


def _resolve_base_dir() -> Path:
    """Return a Path that has an ``algorithmic/`` child, satisfying frontier_cs.

    Order: ``FRONTIER_CS_BASE_DIR`` env var, then a small set of common
    sibling-clone locations relative to this repo. We don't fabricate a
    stub: if the runner ever needs to fall back to ``docker compose``,
    pointing it at a fake directory would mask a real misconfiguration.
    """
    candidates: list[Path] = []
    env = os.environ.get("FRONTIER_CS_BASE_DIR")
    if env:
        candidates.append(Path(env).expanduser())

    here = Path(__file__).resolve()
    # examples/frontier_smith/grader/src/frontier_smith_grader/grader.py
    # → walk up to the directory holding the CORAL repo and look for siblings.
    for parent in here.parents:
        candidates.append(parent / "Frontier-CS")
        if parent.name == "CORAL":
            candidates.append(parent.parent / "Frontier-CS")
            break

    for candidate in candidates:
        if (candidate / "algorithmic").is_dir():
            return candidate

    raise RuntimeError(
        "Could not locate a Frontier-CS checkout. Set FRONTIER_CS_BASE_DIR to "
        "the directory containing 'algorithmic/' (the same checkout running "
        "the judge via docker compose). Searched: "
        + ", ".join(str(c) for c in candidates)
    )


class Grader(TaskGrader):
    """Grader for a single Frontier-Smith algorithmic problem."""

    def evaluate(self) -> ScoreBundle:
        problem_id = self.args.get("problem_id")
        if not problem_id:
            return self.fail("grader arg 'problem_id' is required")

        solution_path = Path(self.codebase_path) / "solution.cpp"
        if not solution_path.exists():
            return self.score(0.0, feedback="No solution.cpp found in workspace.")

        code = solution_path.read_text()
        if not code.strip():
            return self.score(0.0, feedback="solution.cpp is empty.")

        from frontier_cs import SingleEvaluator

        try:
            base_dir = _resolve_base_dir()
        except RuntimeError as exc:
            return self.fail(str(exc))

        evaluator = SingleEvaluator(base_dir=base_dir, register_cleanup=False)
        result = evaluator.evaluate(
            "algorithmic", problem_id=problem_id, code=code,
        )

        if not result.success:
            msg = result.message or "Evaluation failed"
            return self.score(0.0, feedback=msg)

        score = result.score if result.score is not None else 0.0
        return self.score(score, feedback=f"Score: {score:.2f}/100")
