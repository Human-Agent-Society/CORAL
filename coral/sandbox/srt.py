"""Built-in sandbox provider: Anthropic's sandbox-runtime (``srt``).

Everywhere else, CORAL *asks* agents to stay out of ``.coral/private/``
(runtime permission settings, CORAL.md instructions). This provider wraps
each agent subprocess in ``srt``
(https://github.com/anthropic-experimental/sandbox-runtime), which enforces
the same boundaries at the OS level — Seatbelt on macOS, bubblewrap on
Linux — for every runtime uniformly:

- Reads are confined to this run: the agent sees the agent worktrees (its
  own and its siblings' — same-island only in multi-island runs, see
  :func:`_worktree_reads`), the run repo, shared ``.coral/`` state (minus
  ``private/``), the surfaced grader source, the CORAL installation itself
  (so agent-side ``coral`` commands resolve to the same code the manager
  runs), and the toolchain's home dotdirs. Other runs and host secrets
  (``~/.ssh``, ``~/.aws``, ...) are unreadable.
- Writes are allow-listed to the same slice plus /tmp.

Network comes in two modes (``agents.sandbox.network``):

- ``"open"`` — full network access. srt's config schema deliberately
  refuses a wildcard domain allowlist; its sanctioned escape hatch is
  ``network.httpProxyPort``, an external proxy that owns filtering policy.
  :class:`AllowAllProxy` is that proxy with the policy "allow everything".
  Traffic is still proxy-mediated (srt removes direct network access
  structurally), so raw UDP/ICMP and proxy-ignorant clients won't work.
- ``"allowlist"`` — srt runs its own filtering proxies against
  ``agents.sandbox.allowed_domains``.

The per-agent settings JSON lives under ``.coral/private/sandbox/`` — srt
reads it host-side before the sandbox exists, and the sandbox itself then
prevents the agent from tampering with its own policy.
"""

from __future__ import annotations

import json
import logging
import select
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coral.sandbox.protocol import AgentSandboxContext, AgentSandboxSpec

if TYPE_CHECKING:
    from coral.config import AgentConfig, SandboxConfig

logger = logging.getLogger(__name__)

# srt overrides TMPDIR to this path inside the sandbox (unless
# CLAUDE_CODE_TMPDIR is set); it must exist or every mktemp fails.
_SRT_TMPDIR = Path("/tmp/claude")

_INSTALL_HINT = "npm install -g @anthropic-ai/sandbox-runtime"

_LINUX_DEPS = {
    "bwrap": "bubblewrap",
    "socat": "socat",
    "rg": "ripgrep",
}


class SrtSandbox:
    """srt-backed :class:`coral.sandbox.protocol.SandboxProvider`."""

    def __init__(self, cfg: SandboxConfig) -> None:
        self.cfg = cfg
        self._proxy: AllowAllProxy | None = None

    def validate(self, agents: AgentConfig) -> None:
        ensure_sandbox_supported(agents)

    def start(self) -> None:
        """Start the allow-all proxy backing ``network="open"``. Idempotent.

        Allowlist mode needs no run-level resources — srt runs its own
        filtering proxies per agent.
        """
        if self.cfg.network == "open" and self._proxy is None:
            self._proxy = AllowAllProxy()
            port = self._proxy.start()
            logger.info(f"Sandbox network proxy (allow-all) on 127.0.0.1:{port}")

    def stop(self) -> None:
        if self._proxy is not None:
            self._proxy.stop()
            self._proxy = None
            logger.info("Sandbox network proxy stopped")

    def prepare_agent(self, ctx: AgentSandboxContext) -> AgentSandboxSpec:
        """Write the per-agent srt settings file and return the launch spec.

        Regenerated on every (re)start so restarts pick up the current
        proxy port. srt injects the proxy env vars into its child itself;
        the spec's own env only carries the editable-install PYTHONPATH
        shim (see :func:`_cli_pythonpath_shim`), when one is needed.
        """
        settings = build_srt_settings(
            self.cfg,
            worktree_path=ctx.worktree_path,
            coral_dir=ctx.coral_dir,
            repo_dir=ctx.repo_dir,
            shared_dir_name=ctx.shared_dir_name,
            proxy_port=self._proxy.port if self._proxy else None,
            sibling_worktrees=ctx.sibling_worktrees,
        )
        settings_dir = ctx.coral_dir / "private" / "sandbox"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / f"{ctx.agent_id}.json"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

        try:
            _SRT_TMPDIR.mkdir(exist_ok=True)
        except OSError:
            pass  # srt/tools will surface a clearer error if /tmp is unusable

        import coral

        env = _cli_pythonpath_shim(
            ctx.coral_dir.parent,
            Path(coral.__file__).resolve().parent,
            Path(sys.prefix).resolve(),
        )
        return AgentSandboxSpec(
            command_prefix=srt_command_prefix(self.cfg.srt_command, settings_path),
            env=env,
        )


def ensure_sandbox_supported(agents: AgentConfig) -> None:
    """Fail fast with actionable errors when srt sandboxing cannot work here.

    Raises RuntimeError on: unresolvable srt command, missing Linux sandbox
    dependencies, or combination with OS-user isolation (``srt`` must read
    the settings file under ``.coral/private/``, which user isolation locks
    to root — the two mechanisms solve the same problem; pick one).
    """
    if agents.isolate_user:
        raise RuntimeError(
            "agents.sandbox cannot be combined with agents.isolate_user "
            "(set implicitly by run.session=docker). Both isolate the agent "
            "from .coral/private/ — use one or the other."
        )
    # Probe the actual invocation rather than PATH-checking a binary name:
    # the npx default resolves npm -g installs whose bin dir is not on PATH,
    # and --no-install makes the probe fail cleanly (instead of npx fetching
    # the unrelated "srt" registry package) when sandbox-runtime is absent.
    srt_command = agents.sandbox.srt_command
    try:
        probe = subprocess.run(
            [*srt_command, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(
            f"agents.sandbox.enabled=true but `{' '.join(srt_command)}` failed to run ({e}). "
            f"Install sandbox-runtime with: {_INSTALL_HINT}"
        ) from e
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip().splitlines()
        raise RuntimeError(
            f"agents.sandbox.enabled=true but `{' '.join(srt_command)} --version` failed"
            + (f" ({detail[-1]})" if detail else "")
            + f". Install sandbox-runtime with: {_INSTALL_HINT}"
        )
    if sys.platform.startswith("linux"):
        missing = [pkg for binary, pkg in _LINUX_DEPS.items() if shutil.which(binary) is None]
        if missing:
            raise RuntimeError(
                "agents.sandbox.enabled=true but srt's Linux dependencies are "
                f"missing: {', '.join(missing)}. Install them with your package "
                f"manager (e.g. apt-get install {' '.join(missing)})."
            )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` (override wins)."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _runtime_home_paths(shared_dir_name: str) -> list[str]:
    """Home paths a sandboxed agent needs, used for both reads and writes.

    Reads are confined to the run dir, so everything under ``$HOME`` the
    agent toolchain legitimately needs must be allowed back explicitly:
    the runtime CLI's own state dir (sessions/credentials — Claude Code
    cannot run without reading ``~/.claude.json``), and the tool caches the
    stack lives off (uv/coral under ``~/.local`` + ``~/.cache``, node under
    ``~/.nvm`` or npm's cache). Deliberately narrow: broad creds dirs like
    ``~/.ssh``, ``~/.aws``, ``~/.config`` (gh/gcloud tokens) stay denied.
    srt's mandatory protections still deny writes to ``.gitconfig``, shell
    rc files, etc. within these grants.
    """
    home = Path.home()
    paths = [
        str(home / ".cache"),  # uv, pip, and friends
        str(home / ".local"),  # uv tools (incl. coral), uv-managed pythons
        str(home / ".npm"),
        str(home / ".nvm"),  # node itself, when nvm-managed
        str(home / ".gitconfig"),  # git aborts on an unreadable existing config
        str(home / shared_dir_name),  # runtime state: ~/.claude, ~/.codex, ...
    ]
    if shared_dir_name == ".claude":
        paths += [str(home / ".claude.json"), str(home / ".claude.json.backup")]
    elif shared_dir_name == ".opencode":
        paths += [str(home / ".config" / "opencode"), str(home / ".opencode")]
    return paths


def _worktree_island(worktree: Path) -> str | None:
    """Read a worktree's island membership from its .coral_island breadcrumb."""
    try:
        return (worktree / ".coral_island").read_text().strip() or None
    except OSError:
        return None


def _worktree_reads(
    worktree_path: Path, coral_dir: Path, sibling_worktrees: list[Path]
) -> list[str]:
    """Agent worktrees this agent may read.

    Reading (not writing) siblings' trees is part of the shared-knowledge
    design, so single-island runs grant the whole ``agents/`` dir — which
    also covers agents spawned later. Multi-island runs stop at the island
    boundary: islands evolve independently and exchange work only through
    migration, so a cross-island read would defeat the diversity the
    partition exists to create. The island-mate roster comes from the
    manager (``ctx.sibling_worktrees`` — correct even before those
    worktrees exist on disk; srt rules are plain path patterns); without
    one, membership falls back to each worktree's ``.coral_island``
    breadcrumb. Either way the grant is rebuilt at every agent (re)start —
    migration updates the roster before restarting the migrant, and
    bystanders pick up the new boundary at their own next restart.
    """
    agents_dir = worktree_path.parent
    if not (coral_dir / "islands").exists():
        return [str(agents_dir.resolve())]
    reads = {str(worktree_path.resolve())}
    if sibling_worktrees:
        reads.update(str(p.resolve()) for p in sibling_worktrees)
    else:
        own = _worktree_island(worktree_path)
        for sibling in agents_dir.iterdir() if own is not None else ():
            if sibling.is_dir() and _worktree_island(sibling) == own:
                reads.add(str(sibling.resolve()))
    return sorted(reads)


def _run_dir_reads(
    worktree_path: Path, coral_dir: Path, repo_dir: Path, sibling_worktrees: list[Path]
) -> list[str]:
    """Run-dir paths this agent may read.

    Enumerated per-child instead of granting the run dir wholesale because
    srt's read rules are allow-beats-deny: an ``allowRead`` on any ancestor
    of ``.coral/private/`` would resurrect it. Other runs are simply never
    allowed back.
    """
    reads = [
        *_worktree_reads(worktree_path, coral_dir, sibling_worktrees),
        str(repo_dir.resolve()),  # run repo (worktree git ops read its .git)
        str((coral_dir / "public").resolve()),
        str((coral_dir / "islands").resolve()),  # multi-island shared state
        str((coral_dir / ".git").resolve()),  # checkpoint history (coral notes --history)
        str((coral_dir / "config.yaml").resolve()),
        str((coral_dir / "config_dir").resolve()),  # breadcrumb read by hooks
        # PYTHONPATH shim for editable installs (_cli_pythonpath_shim). Not
        # under allowWrite, so agents cannot repoint the symlink.
        str((coral_dir.parent / ".sandbox").resolve()),
    ]
    # The grader source is surfaced to agents as <shared_dir>/grader — a
    # symlink whose target (the task's grader/ package) lives outside the
    # run dir. Allow exactly that target; the task dir's other siblings
    # (e.g. the hidden taskdata/ that grader.private copies) stay denied.
    from coral.workspace.worktree import grader_source_dir

    grader_source = grader_source_dir(coral_dir)
    if grader_source is not None:
        reads.append(str(grader_source.resolve()))
    return reads


def _coral_install_reads() -> list[str]:
    """Paths of the CORAL installation driving this run.

    Agents invoke the bare ``coral`` CLI, which must resolve to the same
    installation the manager runs — otherwise the shell's PATH search
    silently falls through to whatever older ``coral`` is readable (e.g. a
    stale ``uv tool install``), and its hooks write attempts where this
    run's daemon never looks. A dev checkout's venv and editable source
    live under ``$HOME`` (denied wholesale), so allow back exactly the
    interpreter prefix (venv: entry script, deps) and the ``coral`` package
    dir (editable installs keep it outside the prefix). Never the checkout
    root: an ``allowRead`` there would resurrect sibling runs' ``.coral/
    private/`` via allow-beats-deny.
    """
    import coral

    return [
        str(Path(sys.prefix).resolve()),
        str(Path(coral.__file__).resolve().parent),
    ]


def _cli_pythonpath_shim(run_dir: Path, package_dir: Path, prefix: Path) -> dict[str, str]:
    """Make an editable-installed ``coral`` importable inside the sandbox.

    An editable install's ``.pth`` puts the *checkout root* on ``sys.path``,
    and Python's import machinery must ``listdir()`` every path entry — but
    the root can never be allowed back (sibling runs' ``.coral/private/``
    live under it, and srt reads are allow-beats-deny). Same trick as the
    surfaced grader source: expose the package through a shim directory
    inside the run dir holding a single symlink, and put that on
    ``PYTHONPATH``. Seatbelt evaluates the resolved target, which
    :func:`_coral_install_reads` already allows. Non-editable installs
    (package inside the interpreter prefix) need nothing.
    """
    if package_dir.is_relative_to(prefix):
        return {}
    shim_dir = run_dir / ".sandbox" / "pythonpath"
    shim_dir.mkdir(parents=True, exist_ok=True)
    link = shim_dir / package_dir.name
    link.unlink(missing_ok=True)  # repoint if the checkout moved since last start
    link.symlink_to(package_dir)
    return {"PYTHONPATH": str(shim_dir)}


def build_srt_settings(
    cfg: SandboxConfig,
    *,
    worktree_path: Path,
    coral_dir: Path,
    repo_dir: Path,
    shared_dir_name: str,
    proxy_port: int | None,
    sibling_worktrees: list[Path] | None = None,
) -> dict[str, Any]:
    """Build the srt settings JSON for one agent.

    Reads are confined to this run: the user's home is denied wholesale and
    only the agent's own slice of the run dir (worktree, repo, shared
    ``.coral`` state minus ``private/``, the surfaced grader source) plus
    the toolchain's home dotdirs are allowed back. System paths (/usr,
    /opt, ...) stay readable so binaries and libraries work. Writes are
    allow-listed to the same slice.
    """
    private_dir = str((coral_dir / "private").resolve())
    home_paths = _runtime_home_paths(shared_dir_name)

    settings: dict[str, Any] = {
        "network": {
            "allowedDomains": list(cfg.allowed_domains),
            "deniedDomains": [],
            # Agents routinely bind localhost ports (dev servers, test suites).
            "allowLocalBinding": True,
        },
        "filesystem": {
            # private_dir is listed even though home already covers the
            # default layout — runs placed outside $HOME (workspace.run_dir)
            # must still hide it.
            "denyRead": [str(Path.home()), private_dir, *cfg.deny_read],
            "allowRead": [
                *_run_dir_reads(worktree_path, coral_dir, repo_dir, sibling_worktrees or []),
                *_coral_install_reads(),
                *home_paths,
                *cfg.allow_read,
            ],
            "allowWrite": [
                str(worktree_path.resolve()),
                # Notes, attempts, eval logs, and the checkpoint repo all live
                # under .coral/ and are written from agent-side `coral` commands.
                str(coral_dir.resolve()),
                # Worktree commits (coral eval) write objects/refs into the
                # run repo's .git; srt's built-in protections still deny
                # .git/hooks and .git/config within it.
                str((repo_dir / ".git").resolve()),
                *home_paths,
                "/tmp",
                "/private/tmp",  # macOS: /tmp resolves here
                *cfg.allow_write,
            ],
            "denyWrite": [private_dir],
        },
        # Runtime CLIs allocate ptys for their shell tools (macOS-only knob).
        "allowPty": True,
    }

    if cfg.network == "open":
        if proxy_port is None:
            raise ValueError("sandbox.network='open' requires a running allow-all proxy")
        settings["network"]["httpProxyPort"] = proxy_port
    else:
        # The srt CLI registers no ask-callback, so unmatched hosts are denied
        # regardless; strictAllowlist documents that this list is policy.
        settings["network"]["strictAllowlist"] = True

    return _deep_merge(settings, cfg.extra_settings)


def srt_command_prefix(srt_command: list[str], settings_path: Path) -> list[str]:
    """Command prefix that wraps a runtime command in the srt sandbox.

    The trailing ``--`` makes srt's CLI treat the entire runtime command as
    positional arguments, so runtime flags (``-p``, ``-c``, ``--model``) can
    never collide with srt's own options.
    """
    return [*srt_command, "--settings", str(settings_path), "--"]


class AllowAllProxy:
    """Minimal allow-all HTTP forward proxy backing ``sandbox.network: open``.

    Handles CONNECT tunnels (all HTTPS/TLS traffic — git, pip, npm, model
    APIs) and single-request absolute-URI plain HTTP. Runs entirely in
    daemon threads inside the manager process: nothing extra to supervise,
    and it dies with the run.
    """

    _HEAD_LIMIT = 64 * 1024
    _CONNECT_TIMEOUT = 30.0

    def __init__(self, host: str = "127.0.0.1") -> None:
        self._host = host
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self.port: int | None = None

    def start(self) -> int:
        """Bind an ephemeral port and start accepting. Returns the port."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self._host, 0))
        listener.listen(128)
        self._listener = listener
        self.port = listener.getsockname()[1]
        self._thread = threading.Thread(
            target=self._serve, name="coral-sandbox-proxy", daemon=True
        )
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stopping.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stopping.is_set():
            try:
                conn, _addr = self._listener.accept()
            except OSError:
                break  # listener closed by stop()
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            head = self._read_head(conn)
            if head is None:
                return
            request_line, rest = head.split(b"\r\n", 1)
            parts = request_line.decode("latin-1", "replace").split(" ")
            if len(parts) != 3:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            method, target, version = parts
            if method.upper() == "CONNECT":
                self._tunnel(conn, target)
            else:
                self._forward_http(conn, method, target, version, rest)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _read_head(self, conn: socket.socket) -> bytes | None:
        """Read up to and including the request-head terminator."""
        conn.settimeout(self._CONNECT_TIMEOUT)
        head = b""
        while b"\r\n\r\n" not in head:
            if len(head) > self._HEAD_LIMIT:
                return None
            chunk = conn.recv(8192)
            if not chunk:
                return None
            head += chunk
        return head

    @staticmethod
    def _split_host_port(authority: str, default_port: int) -> tuple[str, int]:
        if authority.startswith("["):  # [ipv6]:port
            host, _, rest = authority[1:].partition("]")
            port = int(rest[1:]) if rest.startswith(":") else default_port
            return host, port
        host, sep, port_s = authority.rpartition(":")
        if sep and port_s.isdigit():
            return host, int(port_s)
        return authority, default_port

    def _dial(self, authority: str, default_port: int) -> socket.socket:
        host, port = self._split_host_port(authority, default_port)
        return socket.create_connection((host, port), timeout=self._CONNECT_TIMEOUT)

    def _tunnel(self, conn: socket.socket, target: str) -> None:
        """CONNECT: open a raw tunnel and relay bytes both ways."""
        try:
            upstream = self._dial(target, 443)
        except OSError:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        with upstream:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self._relay(conn, upstream)

    def _forward_http(
        self, conn: socket.socket, method: str, target: str, version: str, rest: bytes
    ) -> None:
        """Absolute-URI plain HTTP: rewrite to origin-form and relay.

        Transparent single-request forwarding (each keep-alive request on
        this connection must target the same host, which real clients do).
        Plain HTTP through a proxy is rare — HTTPS goes via CONNECT above.
        """
        if "://" not in target:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        authority_and_path = target.split("://", 1)[1]
        authority, slash, path = authority_and_path.partition("/")
        try:
            upstream = self._dial(authority, 80)
        except OSError:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        with upstream:
            origin_line = f"{method} {slash + path or '/'} {version}".encode("latin-1")
            upstream.sendall(origin_line + b"\r\n" + rest)
            self._relay(conn, upstream)

    @staticmethod
    def _relay(a: socket.socket, b: socket.socket) -> None:
        """Shuttle bytes between two sockets until either side closes."""
        a.settimeout(None)
        b.settimeout(None)
        sockets = [a, b]
        peer = {a: b, b: a}
        while True:
            readable, _, errored = select.select(sockets, [], sockets, 300)
            if errored or not readable:
                return
            for sock in readable:
                try:
                    data = sock.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                try:
                    peer[sock].sendall(data)
                except OSError:
                    return
