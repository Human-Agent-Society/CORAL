"""Tests for pluggable agent sandboxing (coral/sandbox/)."""

from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from coral.config import AgentConfig, CoralConfig, SandboxConfig
from coral.sandbox import (
    AgentSandboxContext,
    AgentSandboxSpec,
    SandboxProvider,
    get_sandbox_provider,
)
from coral.sandbox.srt import (
    AllowAllProxy,
    SrtSandbox,
    _cli_pythonpath_shim,
    _tls_cert_env,
    build_srt_settings,
    ensure_sandbox_supported,
    srt_command_prefix,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_sandbox_config_defaults():
    cfg = SandboxConfig()
    assert cfg.enabled is False
    assert cfg.provider == "srt"
    assert cfg.network == "open"
    assert cfg.allowed_domains == []
    assert cfg.srt_command == ["npx", "--no-install", "srt"]


def test_sandbox_config_rejects_bad_network():
    with pytest.raises(ValueError, match="'open' or 'allowlist'"):
        SandboxConfig(network="unrestricted")


def test_sandbox_config_rejects_empty_provider():
    with pytest.raises(ValueError, match="provider"):
        SandboxConfig(provider="")


def test_sandbox_and_isolate_user_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        AgentConfig(isolate_user="agent", sandbox=SandboxConfig(enabled=True))


def test_agent_config_coerces_sandbox_dict():
    cfg = AgentConfig(sandbox={"enabled": True, "network": "allowlist"})
    assert isinstance(cfg.sandbox, SandboxConfig)
    assert cfg.sandbox.enabled is True
    assert cfg.sandbox.network == "allowlist"


def test_sandbox_config_parses_from_task_yaml_dict():
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {
                "sandbox": {
                    "enabled": True,
                    "network": "allowlist",
                    "allowed_domains": ["github.com", "*.npmjs.org"],
                }
            },
        }
    )
    assert cfg.agents.sandbox.enabled is True
    assert cfg.agents.sandbox.allowed_domains == ["github.com", "*.npmjs.org"]


def test_sandbox_preset_enables_sandbox():
    cfg = CoralConfig.from_dict({"task": {"name": "t", "description": "d"}, "preset": "sandbox"})
    assert cfg.agents.sandbox.enabled is True
    assert cfg.agents.sandbox.network == "open"


# ---------------------------------------------------------------------------
# Registry / protocol
# ---------------------------------------------------------------------------


class DummyProvider:
    """Minimal out-of-tree provider used to exercise the entrypoint path."""

    def __init__(self, cfg: SandboxConfig) -> None:
        self.cfg = cfg

    def validate(self, agents: AgentConfig) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def prepare_agent(self, ctx: AgentSandboxContext) -> AgentSandboxSpec:
        return AgentSandboxSpec(command_prefix=["dummy-exec", "--"], env={"DUMMY": "1"})


def test_registry_resolves_builtin_srt():
    provider = get_sandbox_provider(SandboxConfig(enabled=True))
    assert isinstance(provider, SrtSandbox)
    assert isinstance(provider, SandboxProvider)


def test_registry_resolves_custom_entrypoint():
    cfg = SandboxConfig(enabled=True, provider="tests.test_sandbox:DummyProvider")
    provider = get_sandbox_provider(cfg)
    assert isinstance(provider, DummyProvider)
    assert isinstance(provider, SandboxProvider)
    assert provider.cfg is cfg


def test_registry_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown sandbox provider"):
        get_sandbox_provider(SandboxConfig(enabled=True, provider="e2b"))


def test_registry_rejects_unloadable_entrypoint():
    with pytest.raises(ValueError, match="Cannot load"):
        get_sandbox_provider(SandboxConfig(enabled=True, provider="no.such.module:Nope"))


# ---------------------------------------------------------------------------
# srt settings generation
# ---------------------------------------------------------------------------


def _paths(tmp_path: Path) -> dict[str, Path | str]:
    worktree = tmp_path / "agents" / "agent-1"
    coral_dir = tmp_path / ".coral"
    repo_dir = tmp_path / "repo"
    for p in (worktree, coral_dir / "private", coral_dir / "public", repo_dir / ".git"):
        p.mkdir(parents=True)
    return {
        "worktree_path": worktree,
        "coral_dir": coral_dir,
        "repo_dir": repo_dir,
        "shared_dir_name": ".claude",
    }


def test_build_settings_reads_confined_to_run(tmp_path):
    paths = _paths(tmp_path)
    settings = build_srt_settings(SandboxConfig(enabled=True), proxy_port=12345, **paths)

    fs = settings["filesystem"]
    private = str((tmp_path / ".coral" / "private").resolve())
    # Home is denied wholesale; the run slice + toolchain dotdirs come back.
    assert str(Path.home()) in fs["denyRead"]
    assert private in fs["denyRead"]
    allow_read = fs["allowRead"]
    # The agents/ parent grants every worktree — reading siblings' trees is
    # part of the shared-knowledge design; writes stay own-worktree-only.
    assert str((tmp_path / "agents").resolve()) in allow_read
    assert str((tmp_path / "repo").resolve()) in allow_read
    assert str((tmp_path / ".coral" / "public").resolve()) in allow_read
    assert str(Path.home() / ".claude") in allow_read
    assert str(Path.home() / ".claude.json") in allow_read
    # Nothing allowed back may be an ancestor of private/ — srt read rules
    # are allow-beats-deny, so an ancestor grant would resurrect it.
    for path in allow_read:
        assert not private.startswith(path + "/") and path != private


def test_build_settings_writes(tmp_path):
    paths = _paths(tmp_path)
    settings = build_srt_settings(SandboxConfig(enabled=True), proxy_port=12345, **paths)

    fs = settings["filesystem"]
    private = str((tmp_path / ".coral" / "private").resolve())
    assert private in fs["denyWrite"]
    assert str((tmp_path / "agents" / "agent-1").resolve()) in fs["allowWrite"]
    assert str((tmp_path / ".coral").resolve()) in fs["allowWrite"]
    assert str((tmp_path / "repo" / ".git").resolve()) in fs["allowWrite"]
    # Home is NOT writable wholesale — only the toolchain dotdirs.
    assert str(Path.home()) not in fs["allowWrite"]
    assert str(Path.home() / ".claude") in fs["allowWrite"]


def test_build_settings_grader_source_readable(tmp_path):
    paths = _paths(tmp_path)
    # Simulate a task dir with a grader package, referenced by the
    # .coral/config_dir breadcrumb (how grader_source_dir resolves it).
    task_dir = tmp_path / "task"
    (task_dir / "grader").mkdir(parents=True)
    (task_dir / "taskdata").mkdir()  # hidden-data sibling must stay denied
    (paths["coral_dir"] / "config_dir").write_text(str(task_dir))

    settings = build_srt_settings(SandboxConfig(enabled=True), proxy_port=1, **paths)
    allow_read = settings["filesystem"]["allowRead"]
    assert str((task_dir / "grader").resolve()) in allow_read
    assert str((task_dir / "taskdata").resolve()) not in allow_read


def test_build_settings_coral_install_readable(tmp_path):
    """Agents must resolve `coral` to the manager's own installation.

    Without these grants a dev checkout's venv is unreadable in the sandbox
    and the shell's PATH search silently falls through to whatever stale
    `coral` is readable (e.g. an old uv tool install), whose hooks write
    attempts where this run's daemon never looks.
    """
    import coral as coral_pkg

    settings = build_srt_settings(SandboxConfig(enabled=True), proxy_port=1, **_paths(tmp_path))
    allow_read = settings["filesystem"]["allowRead"]
    assert str(Path(sys.prefix).resolve()) in allow_read
    assert str(Path(coral_pkg.__file__).resolve().parent) in allow_read


def test_build_settings_multi_island_roster(tmp_path):
    """The manager's island-mate roster drives worktree reads — including
    worktrees that don't exist on disk yet (initial start spawns agents one
    by one, so later island-mates are pre-granted by path)."""
    paths = _paths(tmp_path)
    (tmp_path / ".coral" / "islands").mkdir()
    own = tmp_path / "agents" / "agent-1"
    unborn_mate = tmp_path / "agents" / "agent-2"  # deliberately not created
    foreigner = tmp_path / "agents" / "agent-3"
    foreigner.mkdir()

    allow_read = build_srt_settings(
        SandboxConfig(enabled=True),
        proxy_port=1,
        sibling_worktrees=[own, unborn_mate],
        **paths,
    )["filesystem"]["allowRead"]
    assert str(own.resolve()) in allow_read
    assert str(unborn_mate.resolve()) in allow_read
    assert str(foreigner.resolve()) not in allow_read
    assert str((tmp_path / "agents").resolve()) not in allow_read


def test_build_settings_multi_island_breadcrumb_fallback(tmp_path):
    """Without a roster (direct API use), island membership falls back to
    each worktree's .coral_island breadcrumb — reads stop at the island
    boundary; islands exchange work only through migration."""
    paths = _paths(tmp_path)
    (tmp_path / ".coral" / "islands").mkdir()
    own = tmp_path / "agents" / "agent-1"
    (own / ".coral_island").write_text("avalon\n")
    islandmate = tmp_path / "agents" / "agent-2"
    islandmate.mkdir()
    (islandmate / ".coral_island").write_text("avalon\n")
    foreigner = tmp_path / "agents" / "agent-3"
    foreigner.mkdir()
    (foreigner / ".coral_island").write_text("atlantis\n")

    allow_read = build_srt_settings(SandboxConfig(enabled=True), proxy_port=1, **paths)[
        "filesystem"
    ]["allowRead"]
    assert str(own.resolve()) in allow_read
    assert str(islandmate.resolve()) in allow_read
    assert str(foreigner.resolve()) not in allow_read
    assert str((tmp_path / "agents").resolve()) not in allow_read


def test_cli_pythonpath_shim_editable_install(tmp_path):
    """Editable installs get a symlink shim on PYTHONPATH — the .pth path
    entry (the checkout root) can never be allowed back in the sandbox."""
    run_dir = tmp_path / "run"
    prefix = tmp_path / "venv"
    prefix.mkdir()
    pkg = tmp_path / "checkout" / "coral"
    pkg.mkdir(parents=True)

    env = _cli_pythonpath_shim(run_dir, pkg, prefix)
    shim = run_dir / ".sandbox" / "pythonpath"
    assert env == {"PYTHONPATH": str(shim)}
    assert (shim / "coral").readlink() == pkg

    # Re-preparing repoints the symlink when the checkout moved.
    pkg2 = tmp_path / "checkout2" / "coral"
    pkg2.mkdir(parents=True)
    _cli_pythonpath_shim(run_dir, pkg2, prefix)
    assert (shim / "coral").readlink() == pkg2


def test_cli_pythonpath_shim_noop_for_normal_install(tmp_path):
    """A coral installed inside the interpreter prefix needs no shim —
    sys.prefix is already in allowRead."""
    prefix = tmp_path / "venv"
    pkg = prefix / "lib" / "site-packages" / "coral"
    pkg.mkdir(parents=True)

    assert _cli_pythonpath_shim(tmp_path / "run", pkg, prefix) == {}
    assert not (tmp_path / "run" / ".sandbox").exists()


def test_tls_cert_env_respects_existing_override(monkeypatch):
    """A user-set SSL_CERT_FILE propagates via the inherited environment —
    the spec must not clobber it."""
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/bundle.pem")
    assert _tls_cert_env() == {}


def test_tls_cert_env_points_at_pem_bundle(monkeypatch):
    """rustls clients (codex) cannot query the macOS keychain inside the
    sandbox; the spec points them at the host's PEM bundle instead."""
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    env = _tls_cert_env()
    if env:  # host has a bundle at a known path (macOS/Linux defaults)
        assert Path(env["SSL_CERT_FILE"]).is_file()
    else:  # no known bundle on this host — nothing to point at
        assert not any(
            Path(p).is_file() for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt")
        )


def test_build_settings_open_mode_network(tmp_path):
    settings = build_srt_settings(SandboxConfig(enabled=True), proxy_port=12345, **_paths(tmp_path))
    # Open mode: no domain allowlist, all traffic via the external proxy.
    assert settings["network"]["allowedDomains"] == []
    assert settings["network"]["httpProxyPort"] == 12345
    assert "strictAllowlist" not in settings["network"]


def test_build_settings_open_mode_requires_proxy(tmp_path):
    with pytest.raises(ValueError, match="allow-all proxy"):
        build_srt_settings(SandboxConfig(enabled=True), proxy_port=None, **_paths(tmp_path))


def test_build_settings_allowlist_mode(tmp_path):
    cfg = SandboxConfig(enabled=True, network="allowlist", allowed_domains=["github.com"])
    settings = build_srt_settings(cfg, proxy_port=None, **_paths(tmp_path))
    assert settings["network"]["allowedDomains"] == ["github.com"]
    assert settings["network"]["strictAllowlist"] is True
    assert "httpProxyPort" not in settings["network"]


def test_build_settings_extra_paths_and_deep_merge(tmp_path):
    cfg = SandboxConfig(
        enabled=True,
        deny_read=["/opt/secrets"],
        allow_read=["/opt/datasets"],
        allow_write=["/scratch"],
        extra_settings={
            "enableWeakerNestedSandbox": True,
            "network": {"allowLocalBinding": False},
        },
    )
    settings = build_srt_settings(cfg, proxy_port=1, **_paths(tmp_path))
    assert "/opt/secrets" in settings["filesystem"]["denyRead"]
    assert "/opt/datasets" in settings["filesystem"]["allowRead"]
    assert "/scratch" in settings["filesystem"]["allowWrite"]
    # extra_settings deep-merges: sibling network keys survive, override wins.
    assert settings["enableWeakerNestedSandbox"] is True
    assert settings["network"]["allowLocalBinding"] is False
    assert settings["network"]["httpProxyPort"] == 1


def test_srt_command_prefix_ends_with_separator():
    # The trailing "--" is load-bearing: without it, runtime flags like -c
    # or -p would be parsed as srt's own options.
    prefix = srt_command_prefix(["npx", "--no-install", "srt"], Path("/x.json"))
    assert prefix == ["npx", "--no-install", "srt", "--settings", "/x.json", "--"]


# ---------------------------------------------------------------------------
# SrtSandbox provider lifecycle
# ---------------------------------------------------------------------------


def _ctx(paths: dict[str, Path | str]) -> AgentSandboxContext:
    return AgentSandboxContext(
        agent_id="agent-1",
        worktree_path=paths["worktree_path"],
        coral_dir=paths["coral_dir"],
        repo_dir=paths["repo_dir"],
        shared_dir_name=paths["shared_dir_name"],
    )


def test_srt_provider_open_mode_lifecycle(tmp_path):
    paths = _paths(tmp_path)
    provider = SrtSandbox(SandboxConfig(enabled=True, srt_command=["srt"]))
    provider.start()
    try:
        assert provider._proxy is not None
        port = provider._proxy.port
        spec = provider.prepare_agent(_ctx(paths))
        settings_path = paths["coral_dir"] / "private" / "sandbox" / "agent-1.json"
        assert settings_path.exists()
        assert json.loads(settings_path.read_text())["network"]["httpProxyPort"] == port
        assert spec.command_prefix == ["srt", "--settings", str(settings_path), "--"]
        # srt injects proxy env into its child itself; the spec's own env
        # carries at most the editable-install PYTHONPATH shim (present when
        # this test runs from a dev checkout, absent for normal installs)
        # and the SSL_CERT_FILE override for rustls clients (present when
        # the host has a PEM bundle at a known path).
        assert set(spec.env) <= {"PYTHONPATH", "SSL_CERT_FILE"}
    finally:
        provider.stop()
    assert provider._proxy is None


def test_srt_provider_allowlist_mode_needs_no_proxy(tmp_path):
    paths = _paths(tmp_path)
    provider = SrtSandbox(
        SandboxConfig(enabled=True, network="allowlist", allowed_domains=["github.com"])
    )
    provider.start()
    assert provider._proxy is None
    spec = provider.prepare_agent(_ctx(paths))
    settings_path = paths["coral_dir"] / "private" / "sandbox" / "agent-1.json"
    assert "httpProxyPort" not in json.loads(settings_path.read_text())["network"]
    assert spec.command_prefix[:3] == ["npx", "--no-install", "srt"]
    provider.stop()


# ---------------------------------------------------------------------------
# Claude Code permission mode under containment
# ---------------------------------------------------------------------------


def test_claude_permission_args_bypass_under_containment():
    from coral.agent.builtin.claude_code import _permission_args

    spec = AgentSandboxSpec(command_prefix=["srt", "--"])
    user = {"uid": 1000, "gid": 1000, "home": "/home/agent"}
    assert _permission_args(spec, None) == ["--dangerously-skip-permissions"]
    assert _permission_args(None, user) == ["--dangerously-skip-permissions"]
    assert _permission_args(spec, user) == ["--dangerously-skip-permissions"]
    # Unconfined agents keep the advisory permission system in auto mode.
    assert _permission_args(None, None) == ["--permission-mode", "auto"]


# ---------------------------------------------------------------------------
# Agent state marking
# ---------------------------------------------------------------------------


def test_agent_state_records_sandbox_provider():
    from coral.agent.state import AgentRuntimeState

    state = AgentRuntimeState(sandbox="srt")
    assert AgentRuntimeState.from_dict(state.to_dict()).sandbox == "srt"
    # Documents written before the field existed read back as unsandboxed.
    assert AgentRuntimeState.from_dict({"state": "active"}).sandbox is None


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _mock_srt_probe(monkeypatch, returncode: int = 0, stderr: str = ""):
    """Replace the `srt --version` probe subprocess with a canned result."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout="1.0.0", stderr=stderr)

    monkeypatch.setattr("coral.sandbox.srt.subprocess.run", fake_run)


def test_preflight_unresolvable_srt_command(monkeypatch):
    _mock_srt_probe(monkeypatch, returncode=1, stderr="npm error could not determine executable")
    with pytest.raises(RuntimeError, match="sandbox-runtime"):
        ensure_sandbox_supported(AgentConfig(sandbox=SandboxConfig(enabled=True)))


def test_preflight_missing_npx(monkeypatch):
    def raise_missing(cmd, **kwargs):
        raise FileNotFoundError("npx")

    monkeypatch.setattr("coral.sandbox.srt.subprocess.run", raise_missing)
    with pytest.raises(RuntimeError, match="sandbox-runtime"):
        ensure_sandbox_supported(AgentConfig(sandbox=SandboxConfig(enabled=True)))


def test_preflight_rejects_isolate_user(monkeypatch):
    _mock_srt_probe(monkeypatch)
    agents = AgentConfig(sandbox=SandboxConfig(enabled=True))
    agents.isolate_user = "agent"  # set post-construction, like the Docker session does
    with pytest.raises(RuntimeError, match="isolate_user"):
        ensure_sandbox_supported(agents)


def test_preflight_passes_with_srt(monkeypatch):
    _mock_srt_probe(monkeypatch)
    monkeypatch.setattr("coral.sandbox.srt.sys.platform", "darwin")
    ensure_sandbox_supported(AgentConfig(sandbox=SandboxConfig(enabled=True)))


def test_preflight_missing_linux_deps(monkeypatch):
    _mock_srt_probe(monkeypatch)
    monkeypatch.setattr("coral.sandbox.srt.shutil.which", lambda binary: None)
    monkeypatch.setattr("coral.sandbox.srt.sys.platform", "linux")
    with pytest.raises(RuntimeError, match="bubblewrap"):
        ensure_sandbox_supported(AgentConfig(sandbox=SandboxConfig(enabled=True)))


# ---------------------------------------------------------------------------
# Allow-all proxy
# ---------------------------------------------------------------------------


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture
def local_http_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address
    server.shutdown()


@pytest.fixture
def proxy():
    p = AllowAllProxy()
    p.start()
    yield p
    p.stop()


def test_proxy_plain_http_forwarding(proxy, local_http_server):
    host, port = local_http_server
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{proxy.port}"})
    )
    with opener.open(f"http://{host}:{port}/", timeout=10) as resp:
        assert resp.status == 200
        assert resp.read() == b"ok"


def test_proxy_connect_tunnel(proxy, local_http_server):
    host, port = local_http_server
    with socket.create_connection(("127.0.0.1", proxy.port), timeout=10) as conn:
        conn.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
        response = conn.recv(4096)
        assert response.startswith(b"HTTP/1.1 200")
        # Speak plain HTTP through the tunnel to prove bytes relay both ways.
        conn.sendall(f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        assert b"200" in data and data.endswith(b"ok")


def test_proxy_connect_unreachable_target_returns_502(proxy):
    # Grab a port with no listener.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()

    with socket.create_connection(("127.0.0.1", proxy.port), timeout=10) as conn:
        conn.sendall(f"CONNECT 127.0.0.1:{dead_port} HTTP/1.1\r\n\r\n".encode())
        assert conn.recv(4096).startswith(b"HTTP/1.1 502")


def test_proxy_bad_request_line(proxy):
    with socket.create_connection(("127.0.0.1", proxy.port), timeout=10) as conn:
        conn.sendall(b"NONSENSE\r\n\r\n")
        assert conn.recv(4096).startswith(b"HTTP/1.1 400")


def test_proxy_stop_closes_listener():
    p = AllowAllProxy()
    port = p.start()
    p.stop()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)
