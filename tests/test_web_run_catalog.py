"""Dashboard discovery and switching across multiple run catalogs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from coral.web.api import get_runs, switch_run
from coral.web.run_catalog import (
    discover_results_dirs,
    find_catalog_root,
    results_dir_id,
    results_dir_label,
)


def _make_run(results_dir: Path, task: str, run: str, attempts: int = 0) -> Path:
    coral_dir = results_dir / task / run / ".coral"
    attempts_dir = coral_dir / "public" / "attempts"
    attempts_dir.mkdir(parents=True)
    for index in range(attempts):
        attempts_dir.joinpath(f"{index}.json").write_text("{}")
    return coral_dir


def _request(coral_dir: Path, catalog_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                coral_dir=coral_dir,
                results_dir=coral_dir.resolve().parent.parent.parent,
                catalog_root=catalog_root,
            )
        )
    )


def test_discover_results_dirs_finds_project_catalogs_without_descending_into_runs(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    current = project / "experiments" / "fast" / "results"
    previous = project / "experiments" / "baseline" / "results"
    current_coral = _make_run(current, "task-fast", "run-2")
    previous_coral = _make_run(previous, "task-base", "run-1")
    nested_repo = current_coral.parent / "repo"
    (nested_repo / ".git").mkdir(parents=True)

    # These look like catalogs but live in trees discovery deliberately prunes.
    _make_run(current / "task-fast" / "run-2" / "repo" / "results", "nested", "run")
    _make_run(project / "node_modules" / "package" / "results", "ignored", "run")

    assert find_catalog_root(project / "experiments" / "fast", current) == project
    assert find_catalog_root(nested_repo, current) == project
    assert discover_results_dirs(project, current) == (previous.resolve(), current.resolve())
    assert previous_coral.is_dir()
    assert results_dir_label(previous, project) == "experiments/baseline/results"
    assert results_dir_id(previous) == results_dir_id(previous.resolve())


async def test_get_runs_groups_history_by_catalog(tmp_path: Path) -> None:
    project = tmp_path / "project"
    current_results = project / "experiments" / "fast" / "results"
    previous_results = project / "experiments" / "baseline" / "results"
    current_coral = _make_run(current_results, "shared-task", "run-2", attempts=2)
    _make_run(previous_results, "shared-task", "run-1", attempts=1)

    response = await get_runs(_request(current_coral, project))

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["current"] == {
        "root": results_dir_id(current_results),
        "task": "shared-task",
        "run": "run-2",
    }
    assert [root["label"] for root in payload["roots"]] == [
        "experiments/baseline/results",
        "experiments/fast/results",
    ]
    assert [root["tasks"][0]["runs"][0]["attempts"] for root in payload["roots"]] == [
        1,
        2,
    ]
    # The compatibility field remains scoped to the current catalog.
    assert payload["tasks"][0]["runs"][0]["timestamp"] == "run-2"


async def test_switch_run_accepts_only_a_discovered_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    current_results = project / "current" / "results"
    previous_results = project / "previous" / "results"
    current_coral = _make_run(current_results, "task", "run-2")
    previous_coral = _make_run(previous_results, "task", "run-1")
    state = _request(current_coral, project).app.state
    state._switch_lock = asyncio.Lock()

    class Watcher:
        def __init__(self, coral_dir: Path, subscribers=None) -> None:
            self.coral_dir = coral_dir
            self._subscribers = subscribers or []
            self.events = []

        def stop(self) -> None:
            pass

        async def run(self) -> None:
            await asyncio.Event().wait()

        def _broadcast(self, event: dict) -> None:
            self.events.append(event)

    old_watcher = Watcher(current_coral)
    state.watcher = old_watcher
    state._watcher_task = asyncio.create_task(old_watcher.run())
    monkeypatch.setattr("coral.web.events.FileWatcher", Watcher)

    class Request:
        app = SimpleNamespace(state=state)

        async def json(self) -> dict[str, str]:
            return {
                "root": results_dir_id(previous_results),
                "task": "task",
                "run": "run-1",
            }

    response = await switch_run(Request())  # type: ignore[arg-type]

    assert response.status_code == 200
    assert state.coral_dir == previous_coral.resolve()
    assert state.results_dir == previous_results.resolve()
    assert state.watcher.events[0]["data"]["root"] == results_dir_id(previous_results)

    state._watcher_task.cancel()
    try:
        await state._watcher_task
    except asyncio.CancelledError:
        pass


async def test_switch_run_rejects_unknown_catalog(tmp_path: Path) -> None:
    project = tmp_path / "project"
    current_results = project / "current" / "results"
    current_coral = _make_run(current_results, "task", "run-2")

    class Request:
        app = _request(current_coral, project).app

        async def json(self) -> dict[str, str]:
            return {"root": "not-in-catalog", "task": "task", "run": "run-2"}

    response = await switch_run(Request())  # type: ignore[arg-type]

    assert response.status_code == 404
    assert json.loads(response.body) == {"error": "run catalog not found"}


async def test_switch_run_rejects_symlink_outside_catalog(tmp_path: Path) -> None:
    project = tmp_path / "project"
    results_dir = project / "results"
    current_coral = _make_run(results_dir, "task", "run-2")
    external_task = tmp_path / "external-task"
    _make_run(external_task, "ignored", "run-1")
    (results_dir / "linked-task").symlink_to(external_task / "ignored", target_is_directory=True)

    class Request:
        app = _request(current_coral, project).app

        async def json(self) -> dict[str, str]:
            return {
                "root": results_dir_id(results_dir),
                "task": "linked-task",
                "run": "run-1",
            }

    response = await switch_run(Request())  # type: ignore[arg-type]

    assert response.status_code == 404
    assert json.loads(response.body) == {"error": "run not found"}
