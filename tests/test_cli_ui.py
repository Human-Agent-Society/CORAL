"""Tests for the CORAL dashboard CLI helpers."""

from __future__ import annotations

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
