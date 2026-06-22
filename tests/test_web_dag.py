"""DAG endpoint: lineage reconstruction from attempt parent_hash links."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from coral.hub.attempts import write_attempt
from coral.types import Attempt
from coral.web.api import get_dag


def _attempt(commit: str, parent: str | None, score: float) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id="agent-1",
        title=f"attempt {commit}",
        score=score,
        status="improved",
        parent_hash=parent,
        timestamp=f"2026-06-01T10:00:{int(score * 10):02d}Z",
    )


def _request(coral_dir: Path):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coral_dir=coral_dir)),
        path_params={},
    )


async def test_dag_builds_nodes_edges_and_roots(tmp_path):
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    # baseline parent "base000" is NOT an attempt → exp1 is a root.
    write_attempt(coral_dir, _attempt("exp1", "base000", 0.5))
    write_attempt(coral_dir, _attempt("exp2", "exp1", 0.7))
    write_attempt(coral_dir, _attempt("exp3", "exp1", 0.9))  # fork off exp1

    response = await get_dag(_request(coral_dir))
    assert response.status_code == 200
    payload = json.loads(response.body)

    nodes = {n["id"]: n for n in payload["nodes"]}
    assert set(nodes) == {"exp1", "exp2", "exp3"}
    # exp1's parent is unknown → root with parent=None.
    assert nodes["exp1"]["parent"] is None and nodes["exp1"]["is_root"] is True
    assert nodes["exp2"]["parent"] == "exp1"
    assert nodes["exp3"]["parent"] == "exp1"

    edges = {(e["from"], e["to"]) for e in payload["edges"]}
    assert edges == {("exp1", "exp2"), ("exp1", "exp3")}

    # Highest score (maximize default) is flagged best.
    assert nodes["exp3"]["is_best"] is True
    assert nodes["exp1"]["is_best"] is False


async def test_dag_marks_user_best_from_metadata(tmp_path):
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    chosen = _attempt("exp1", None, 0.5)
    chosen.metadata["user_best"] = True
    write_attempt(coral_dir, chosen)
    write_attempt(coral_dir, _attempt("exp2", None, 0.9))

    response = await get_dag(_request(coral_dir))
    payload = json.loads(response.body)

    nodes = {n["id"]: n for n in payload["nodes"]}
    assert nodes["exp1"]["is_best"] is True
    assert nodes["exp1"]["user_best"] is True
    assert nodes["exp2"]["is_best"] is False
