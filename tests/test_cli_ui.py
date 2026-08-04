"""Tests for the CORAL dashboard CLI helpers."""

from __future__ import annotations

import subprocess

import pytest

from coral.cli import _helpers, ui


def test_find_available_port_skips_occupied_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "UI_PORT_SEARCH_LIMIT", 3)
    monkeypatch.setattr(ui, "_port_available", lambda host, port: port == 9002)

    assert ui._find_available_port("127.0.0.1", 9000) == 9002


def test_find_available_port_raises_when_range_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ui, "UI_PORT_SEARCH_LIMIT", 2)
    monkeypatch.setattr(ui, "_port_available", lambda host, port: False)

    with pytest.raises(RuntimeError, match="9000-9001"):
        ui._find_available_port("127.0.0.1", 9000)


def test_resolve_ui_port_uses_fallback_for_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ui, "DEFAULT_UI_PORT", 9000)
    monkeypatch.setattr(ui, "_find_available_port", lambda host, preferred: 9001)

    assert ui._resolve_ui_port("127.0.0.1", None) == 9001
    assert "Dashboard port 9000 is in use; using 9001" in capsys.readouterr().out


def test_resolve_ui_port_rejects_explicit_occupied_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ui, "_port_available", lambda host, port: False)

    with pytest.raises(RuntimeError, match="Dashboard port 9000 is already in use"):
        ui._resolve_ui_port("127.0.0.1", 9000)


def test_start_ui_background_spawns_detached_process(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coral_dir = tmp_path / "results" / "task-a" / "run-1" / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    captured = {}

    class Process:
        pid = 4321

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(ui, "_ensure_ui_deps", lambda: None)
    monkeypatch.setattr(ui, "_ensure_ui_built", lambda: None)
    monkeypatch.setattr(ui, "_port_available", lambda host, port: True)
    monkeypatch.setattr(ui.shutil, "which", lambda command: "/venv/bin/coral")
    monkeypatch.setattr(ui.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: True)

    ui.start_ui_background(coral_dir, port=9000)

    assert captured["command"] == [
        "/venv/bin/coral",
        "ui",
        "--host",
        "127.0.0.1",
        "--port",
        "9000",
        "--task",
        "task-a",
        "--run",
        "run-1",
        "--no-open",
    ]
    assert captured["cwd"] == tmp_path
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True
    assert (coral_dir / "public" / "ui.pid").read_text() == "4321"
    assert (coral_dir / "public" / "ui.url").read_text().strip() == "http://127.0.0.1:9000"


def test_start_ui_background_reuses_live_dashboard(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coral_dir = tmp_path / "results" / "task-a" / "run-1" / ".coral"
    public_dir = coral_dir / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "ui.pid").write_text("4321")
    (public_dir / "ui.url").write_text("http://127.0.0.1:9010\n")
    opened = []

    monkeypatch.setattr(ui, "_ensure_ui_deps", lambda: None)
    monkeypatch.setattr(ui, "_ensure_ui_built", lambda: None)
    monkeypatch.setattr(ui.os, "kill", lambda pid, signal: None)
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        ui.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("a second dashboard should not be spawned"),
    )

    ui.start_ui_background(coral_dir)

    assert opened == ["http://127.0.0.1:9010"]


def test_kill_ui_removes_process_metadata(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    coral_dir = tmp_path / ".coral"
    public_dir = coral_dir / "public"
    public_dir.mkdir(parents=True)
    (public_dir / "ui.pid").write_text("4321")
    (public_dir / "ui.url").write_text("http://127.0.0.1:9010\n")
    killed = []
    monkeypatch.setattr(_helpers.os, "kill", lambda pid, signal: killed.append(pid))

    _helpers.kill_ui(coral_dir)

    assert killed == [4321]
    assert not (public_dir / "ui.pid").exists()
    assert not (public_dir / "ui.url").exists()


def test_quiet_docker_liveness_returns_false_when_docker_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coral_dir = tmp_path / "run" / ".coral"
    coral_dir.mkdir(parents=True)
    (coral_dir.parent / ".coral_docker_container").write_text("coral-test")
    monkeypatch.setattr(_helpers, "_probe_docker_sudo", lambda: None)

    assert _helpers.is_docker_run_alive(coral_dir, quiet=True) is False


def test_docker_liveness_still_exits_when_not_quiet(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coral_dir = tmp_path / "run" / ".coral"
    coral_dir.mkdir(parents=True)
    (coral_dir.parent / ".coral_docker_container").write_text("coral-test")
    monkeypatch.setattr(_helpers, "_probe_docker_sudo", lambda: None)

    with pytest.raises(SystemExit):
        _helpers.is_docker_run_alive(coral_dir)
