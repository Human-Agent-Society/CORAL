"""Web dashboard behavior for multi-island run layouts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from coral.hub.attempts import write_attempt
from coral.types import Attempt
from coral.web.api import get_runs, get_skill_detail, get_status
from coral.web.events import FileWatcher
from coral.web.logs import list_log_files


def _make_attempt(commit: str, agent: str, score: float = 0.5) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title="attempt",
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-06-01T10:00:00Z",
    )


def _make_multi_island(coral_dir: Path) -> None:
    (coral_dir / "public").mkdir(parents=True)
    for island in ("0", "1"):
        for subdir in ("attempts", "logs", "notes", "skills"):
            (coral_dir / "islands" / island / subdir).mkdir(parents=True)


def _request(coral_dir: Path, **path_params):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                coral_dir=coral_dir,
                results_dir=coral_dir.resolve().parent.parent.parent,
            )
        ),
        path_params=path_params,
    )


def test_list_log_files_aggregates_island_logs(tmp_path):
    coral_dir = tmp_path / ".coral"
    _make_multi_island(coral_dir)
    (coral_dir / "islands" / "0" / "logs" / "0-agent-1.0.log").write_text("a")
    (coral_dir / "islands" / "1" / "logs" / "1-agent-1.0.log").write_text("b")

    logs = list_log_files(coral_dir)

    assert set(logs) == {"0-agent-1", "1-agent-1"}
    assert logs["0-agent-1"][0]["island_id"] == "0"
    assert logs["1-agent-1"][0]["island_id"] == "1"


async def test_status_uses_global_eval_count_and_island_logs(tmp_path):
    coral_dir = tmp_path / ".coral"
    _make_multi_island(coral_dir)
    (coral_dir / "eval_count").write_text("7")
    (coral_dir / "islands" / "1" / "logs" / "1-agent-1.0.log").write_text("log")
    write_attempt(coral_dir, _make_attempt("abc", "1-agent-1"), island_id="1")

    response = await get_status(_request(coral_dir))

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["eval_count"] == 7
    assert [a["agent_id"] for a in payload["agents"]] == ["1-agent-1"]


async def test_runs_treats_unqueryable_docker_as_stopped(tmp_path, monkeypatch):
    results_dir = tmp_path / "results"
    coral_dir = results_dir / "task" / "run-1" / ".coral"
    _make_multi_island(coral_dir)
    (coral_dir.parent / ".coral_docker_container").write_text("coral-test")

    from coral.cli import _helpers

    monkeypatch.setattr(_helpers, "_probe_docker_sudo", lambda: None)

    response = await get_runs(_request(coral_dir))

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["tasks"][0]["runs"][0]["status"] == "stopped"


async def test_skill_detail_finds_island_skill(tmp_path):
    coral_dir = tmp_path / ".coral"
    _make_multi_island(coral_dir)
    skill_dir = coral_dir / "islands" / "1" / "skills" / "island-skill"
    skill_dir.mkdir()
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: island-skill\ndescription: Island scoped\n---\nBody\n"
    )

    response = await get_skill_detail(_request(coral_dir, name="island-skill"))

    assert response.status_code == 200
    assert json.loads(response.body)["metadata"]["name"] == "island-skill"


def test_file_watcher_snapshot_scans_island_roots(tmp_path):
    coral_dir = tmp_path / ".coral"
    _make_multi_island(coral_dir)
    (coral_dir / "eval_count").write_text("3")
    write_attempt(coral_dir, _make_attempt("abc", "0-agent-1"), island_id="0")
    note = coral_dir / "islands" / "1" / "notes" / "n.md"
    note.write_text("# n")
    log = coral_dir / "islands" / "0" / "logs" / "0-agent-1.0.log"
    log.write_text("x")
    for path in (note, log):
        path.touch()

    snapshot = FileWatcher(coral_dir)._snapshot()

    assert snapshot["attempts_count"] == 1
    assert snapshot["attempts_mtime"] > 0
    assert snapshot["notes_mtime"] > 0
    assert snapshot["log_sizes"] == {"0/0-agent-1.0.log": 1}
    assert snapshot["eval_count"] == 3
