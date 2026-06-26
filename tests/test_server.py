"""Tests for the host-level `coral server` — serving with no current run."""

from __future__ import annotations

import os
from pathlib import Path

from starlette.testclient import TestClient

from coral.cli.ui import _latest_run_coral_dir
from coral.web.app import create_app


def _placeholder(tmp_path: Path) -> Path:
    cd = tmp_path / "placeholder" / ".coral"
    (cd / "public").mkdir(parents=True)
    return cd


def test_server_serves_without_a_run(tmp_path: Path) -> None:
    """With a placeholder coral_dir + empty runs root, the read endpoints
    return empty instead of crashing, and chat/runs endpoints work."""
    coral_dir = _placeholder(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    app = create_app(coral_dir, results_dir=results)
    with TestClient(app) as c:
        assert c.get("/api/chat/bindings").status_code == 200
        assert c.get("/api/runs").status_code == 200
        attempts = c.get("/api/attempts")
        assert attempts.status_code == 200
        assert attempts.json() == []  # no run data, no crash
        assert c.get("/api/status").status_code == 200


def test_latest_run_coral_dir(tmp_path: Path) -> None:
    results = tmp_path / "results"
    assert _latest_run_coral_dir(results) is None  # missing root
    results.mkdir()
    assert _latest_run_coral_dir(results) is None  # empty root

    older = results / "task-a" / "2026-01-01_00-00-00" / ".coral"
    older.mkdir(parents=True)
    newer = results / "task-a" / "2026-02-01_00-00-00" / ".coral"
    newer.mkdir(parents=True)
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    assert _latest_run_coral_dir(results) == newer
