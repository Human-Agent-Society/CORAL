"""Deterministic harness for ``coral.grader.evolution`` integration tests.

Provides a scripted inner grader with barriers (so a test can hold evaluation
A open while B starts, finishes, and evolves the rubric), a real on-disk CORAL
layout so ``is_finalized`` is exercised rather than mocked, and a stub for the
evolution agent so no network is touched.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coral.config import GraderConfig
from coral.grader.evolution import grader as gmod
from coral.grader.evolution.grader import EvolvingTaskGrader
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle, Task

SCRIPT: dict[str, dict[str, Any]] = {}  # attempt -> {"scores": {...}} | {"fail": "..."}
SEQUENCE: dict[str, list[dict[str, Any]]] = {}  # attempt -> per-call outcomes (retry tests)
BARRIERS: dict[str, threading.Event] = {}  # attempt -> must be set before evaluate() returns
ENTERED: dict[str, threading.Event] = {}  # attempt -> set once inside the inner grader
CALLS: list[tuple[str, tuple[str, ...]]] = []


def reset() -> None:
    for d in (SCRIPT, SEQUENCE, BARRIERS, ENTERED):
        d.clear()
    CALLS.clear()


class FakeInner(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        aid = (
            str((self.tasks[0].metadata or {}).get("commit_hash", "unknown"))
            if self.tasks
            else "unknown"
        )
        names = tuple(c["name"] for c in (self.args.get("criteria") or []))
        CALLS.append((aid, names))
        if aid in ENTERED:
            ENTERED[aid].set()
        if aid in BARRIERS:
            BARRIERS[aid].wait(timeout=10)
        spec = SEQUENCE[aid].pop(0) if SEQUENCE.get(aid) else SCRIPT.get(aid, {"scores": {}})
        if "fail" in spec:
            return ScoreBundle(
                scores={"eval": Score(value=None, name="eval", explanation=spec["fail"])},
                aggregated=None,
                feedback=spec["fail"],
            )
        scored = {n: float(spec.get("scores", {}).get(n, spec.get("default", 0.5))) for n in names}
        for n in spec.get("omit", []):
            scored.pop(n, None)
        weights = {c["name"]: float(c.get("weight", 1.0)) for c in self.args["criteria"]}
        tw = sum(weights[n] for n in scored) or 1.0
        return ScoreBundle(
            scores={n: Score(value=v, name=n) for n, v in scored.items()},
            aggregated=sum(scored[n] * weights[n] for n in scored) / tw,
            feedback="; ".join(f"{n}: {v:.2f}" for n, v in sorted(scored.items())),
        )


class HookedInner(FakeInner):
    """FakeInner that exercises both optional hooks."""

    def evaluator_log_path(self, attempt_id: str) -> Path | None:
        return None

    def classify_failure(self, bundle, log_info):
        from coral.grader.evolution.failures import FailureCode

        if "playwright" in (bundle.feedback or "").casefold():
            return FailureCode.PLAYWRIGHT_UNAVAILABLE
        return None


class TestGrader(EvolvingTaskGrader):
    inner_grader_cls = FakeInner


class HookedGrader(EvolvingTaskGrader):
    inner_grader_cls = HookedInner


@dataclass
class Harness:
    root: Path
    proposals: list[dict[str, Any]] = field(default_factory=list)
    agent_calls: list[str] = field(default_factory=list)

    @property
    def private(self) -> Path:
        p = self.root / "coral" / "private"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def attempts(self) -> Path:
        p = self.root / "coral" / "public" / "attempts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def notes(self) -> Path:
        p = self.root / "coral" / "public" / "notes"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def write_attempt(self, attempt_id: str, status: str = "pending", feedback: str = "") -> None:
        (self.attempts / f"{attempt_id}.json").write_text(
            json.dumps(
                {
                    "commit_hash": attempt_id,
                    "agent_id": "a",
                    "status": status,
                    "score": None if status == "pending" else 0.5,
                    "feedback": feedback,
                }
            )
        )

    def finalize(self, attempt_id: str, status: str = "improved", feedback: str = "") -> None:
        self.write_attempt(attempt_id, status=status, feedback=feedback)

    def is_final(self, attempt_id: str) -> bool:
        p = self.attempts / f"{attempt_id}.json"
        return p.exists() and json.loads(p.read_text()).get("status") not in (None, "pending")

    def grader(
        self,
        attempt_id: str,
        criteria: list[dict[str, Any]],
        evolution: dict[str, Any] | None = None,
        agent_id: str = "a",
        cls: type[EvolvingTaskGrader] = TestGrader,
    ) -> EvolvingTaskGrader:
        args = {
            "criteria": criteria,
            "evaluator_model": "stub",
            "evolution": evolution if evolution is not None else {"mode": "adaptive"},
        }
        g = cls(GraderConfig(entrypoint="x:Y", timeout=60, args=args))
        g.private_dir = str(self.private)
        g.codebase_path = str(self.root)
        g.island_id = None
        g.tasks = [
            Task(
                id="t",
                name="Museum site",
                description="Build a museum website.",
                metadata={"commit_hash": attempt_id, "agent_id": agent_id},
            )
        ]
        return g

    def install_agent_stub(self, monkeypatch) -> None:
        def fake(*, model, prompt, scratch_cwd, timeout=180):
            self.agent_calls.append(prompt)
            return {
                "new_criteria": ground(prompt, [dict(p) for p in self.proposals]),
                "notes": "stub",
            }

        monkeypatch.setattr(gmod.prop, "run_evolution_agent", fake)


def ground(prompt: str, proposals: list[dict]) -> list[dict]:
    """Fill in a source id and a verbatim quote taken from the prompt itself.

    Real proposers must cite a source and quote it exactly; the check is a
    substring match. A stub that returns fixed text would be rejected, so this
    makes the fixtures behave like a compliant proposer rather than disabling
    the check under test.
    """
    m = re.search(r"#### attempt (\S+)\n(.+)", prompt)
    if m:
        src, line = m.group(1), m.group(2).strip()
    else:  # blind prompt: the only quotable source is the brief
        src = "brief"
        body = prompt.split("## The task being evaluated", 1)[-1]
        line = next((x.strip() for x in body.splitlines() if len(x.strip()) > 12), "Build")
    for d in proposals:
        d.setdefault("cited_source_id", src)
        d.setdefault("quote", line[:60])
    return proposals


def proposal(
    name: str,
    description: str = "A task-level quality dimension.",
    weight: float = 1.0,
    feasible: bool = True,
    cited_evidence: str = "",
    task_level: str = "applies to any valid solution",
    generalizes: bool = True,
    source_attempt_ids=None,
    source_note_ids=None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "weight": weight,
        "feasible": feasible,
        "cited_evidence": cited_evidence,
        "task_level_rationale": task_level,
        "applies_to_different_solution_strategies": generalizes,
        "source_attempt_ids": source_attempt_ids or [],
        "source_note_ids": source_note_ids or [],
    }


def criteria(*specs: tuple[str, float, bool]) -> list[dict[str, Any]]:
    return [
        {"name": n, "weight": w, "anchor": a, "description": f"{n} description"}
        for n, w, a in specs
    ]


def run_scored(
    h: Harness,
    attempt_id: str,
    crit,
    scores: dict[str, float],
    evolution: dict[str, Any],
    agent_id: str = "a",
    finalize: bool = True,
    feedback: str | None = None,
    cls=TestGrader,
) -> ScoreBundle:
    SCRIPT[attempt_id] = {"scores": scores}
    h.write_attempt(attempt_id, status="pending")
    bundle = h.grader(attempt_id, crit, evolution, agent_id=agent_id, cls=cls).evaluate()
    if finalize:
        h.finalize(attempt_id, feedback=feedback or bundle.feedback or "")
    return bundle
