"""CLI: user-level agent bindings (`coral setup agent`, `coral agents ...`).

Bindings are machine-local presets that tasks reference by name. See
``coral.user_agents`` for the storage model and ``coral.config._expand_bindings``
for how they expand into concrete runtime/model fields at load time.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from coral.agent.registry import (
    default_command_for_runtime,
    default_model_for_runtime,
    is_known_runtime,
    known_runtimes,
)
from coral.user_agents import AgentBinding, load_store, save_store


def _store_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "config", None)
    return Path(raw).expanduser() if raw else None


def _parse_options(pairs: list[str]) -> dict[str, Any]:
    """Parse ``KEY=VALUE`` option strings into a dict, coercing simple scalars."""
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"Error: --option must be KEY=VALUE, got {pair!r}", file=sys.stderr)
            sys.exit(1)
        key, _, value = pair.partition("=")
        key = key.strip()
        out[key] = _coerce(value.strip())
    return out


def _coerce(value: str) -> Any:
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        resp = input(f"{label}{suffix}: ").strip()
    except EOFError:
        resp = ""
    return resp or default


# --- coral setup agent --------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> None:
    """Dispatch `coral setup <subcommand>`."""
    sub = getattr(args, "setup_command", None)
    if sub == "agent":
        _setup_agent(args)
    else:
        print("Usage: coral setup agent [--name NAME] ...", file=sys.stderr)
        sys.exit(2)


def _setup_agent(args: argparse.Namespace) -> None:
    """Create or update a named agent binding."""
    path = _store_path(args)
    store = load_store(path)

    interactive = not args.non_interactive and sys.stdin.isatty()

    name = args.name
    if not name and interactive:
        name = _prompt("Binding name")
    if not name:
        print("Error: a binding name is required (--name NAME)", file=sys.stderr)
        sys.exit(1)

    existing = store.get(name)

    runtime = args.runtime
    if not runtime and interactive:
        runtime = _prompt(
            f"Runtime ({', '.join(known_runtimes())})",
            default=(existing.runtime if existing else "claude_code"),
        )
    if not runtime:
        runtime = existing.runtime if existing else "claude_code"
    if not is_known_runtime(runtime):
        print(
            f"Error: unknown runtime {runtime!r}. "
            f"Known runtimes: {', '.join(known_runtimes())} "
            f"(or a 'module.path:ClassName' custom entrypoint).",
            file=sys.stderr,
        )
        sys.exit(1)

    command = args.command_path
    if not command and interactive:
        command = _prompt(
            "Command (CLI binary)",
            default=(
                existing.command
                if existing and existing.command
                else (default_command_for_runtime(runtime) or "")
            ),
        )
    if not command:
        command = (
            existing.command
            if existing and existing.command
            else (default_command_for_runtime(runtime) or "")
        )

    model = args.model
    if not model and interactive:
        model = _prompt(
            "Model",
            default=(
                existing.model
                if existing and existing.model
                else (default_model_for_runtime(runtime) or "")
            ),
        )
    if not model:
        model = existing.model if existing and existing.model else ""

    role_file = args.role_file
    if role_file is None and interactive:
        role_file = _prompt(
            "Role seed file (optional)",
            default=(existing.role_file if existing else ""),
        )
    if role_file is None:
        role_file = existing.role_file if existing else ""

    options = _parse_options(args.option or [])
    if existing and not options:
        options = dict(existing.runtime_options)

    binding = AgentBinding(
        name=name,
        runtime=runtime,
        command=command,
        model=model,
        runtime_options=options,
        role_file=role_file,
    )

    store.bindings[name] = binding
    if args.default or store.default is None:
        store.default = name

    written = save_store(store, path)

    verb = "Updated" if existing else "Created"
    print(f"{verb} agent binding '{name}' in {written}")
    _print_binding(binding, is_default=(store.default == name))
    print()
    issues = _validate_binding(binding)
    _print_doctor(binding, issues)


# --- coral agents ... ---------------------------------------------------------


def cmd_agents(args: argparse.Namespace) -> None:
    """Dispatch `coral agents <subcommand>`."""
    sub = getattr(args, "agents_command", None)
    if sub == "list" or sub is None:
        _agents_list(args)
    elif sub == "show":
        _agents_show(args)
    elif sub == "remove":
        _agents_remove(args)
    elif sub == "doctor":
        _agents_doctor(args)
    else:
        print(f"Unknown agents subcommand: {sub}", file=sys.stderr)
        sys.exit(2)


def _agents_list(args: argparse.Namespace) -> None:
    store = load_store(_store_path(args))
    if not store.bindings:
        print(f"No agent bindings defined ({store.path}).")
        print("Create one with `coral setup agent`.")
        return
    print(f"Agent bindings ({store.path}):\n")
    for name in sorted(store.bindings):
        b = store.bindings[name]
        marker = " (default)" if store.default == name else ""
        model = b.model or default_model_for_runtime(b.runtime) or "?"
        print(f"  {name}{marker}")
        print(f"      runtime: {b.runtime}    model: {model}    command: {b.command or '-'}")
        if b.role_file:
            print(f"      role_file: {b.role_file}")
        if b.runtime_options:
            print(f"      runtime_options: {b.runtime_options}")


def _agents_show(args: argparse.Namespace) -> None:
    store = load_store(_store_path(args))
    binding = store.get(args.name)
    if binding is None:
        print(f"Error: no binding named {args.name!r} in {store.path}", file=sys.stderr)
        sys.exit(1)
    _print_binding(binding, is_default=(store.default == args.name))


def _agents_remove(args: argparse.Namespace) -> None:
    path = _store_path(args)
    store = load_store(path)
    if args.name not in store.bindings:
        print(f"Error: no binding named {args.name!r} in {store.path}", file=sys.stderr)
        sys.exit(1)
    del store.bindings[args.name]
    if store.default == args.name:
        store.default = next(iter(sorted(store.bindings)), None)
    save_store(store, path)
    print(f"Removed agent binding '{args.name}'.")


def _agents_doctor(args: argparse.Namespace) -> None:
    store = load_store(_store_path(args))
    if not store.bindings:
        print(f"No agent bindings defined ({store.path}).")
        return
    name = getattr(args, "name", None)
    if name:
        binding = store.get(name)
        if binding is None:
            print(f"Error: no binding named {name!r} in {store.path}", file=sys.stderr)
            sys.exit(1)
        targets = [binding]
    else:
        targets = [store.bindings[n] for n in sorted(store.bindings)]

    any_fail = False
    for binding in targets:
        issues = _validate_binding(binding)
        ok = _print_doctor(binding, issues)
        any_fail = any_fail or not ok
    sys.exit(1 if any_fail else 0)


# --- shared helpers -----------------------------------------------------------


def _print_binding(binding: AgentBinding, is_default: bool = False) -> None:
    marker = " (default)" if is_default else ""
    print(f"binding: {binding.name}{marker}")
    print(f"  runtime:         {binding.runtime}")
    print(f"  command:         {binding.command or '-'}")
    print(f"  model:           {binding.model or '(runtime default)'}")
    print(f"  role_file:       {binding.role_file or '-'}")
    print(f"  runtime_options: {binding.runtime_options or '{}'}")


def _validate_binding(binding: AgentBinding) -> list[tuple[str, bool, str]]:
    """Run lightweight, non-invasive checks. Returns (label, ok, detail) rows.

    Checks never store or transmit credentials. Authentication is not probed
    invasively — when it cannot be checked safely we say so and defer to the
    runtime-native login flow.
    """
    rows: list[tuple[str, bool, str]] = []

    # 1. Runtime resolves and the config compiles to a valid AgentSpec.
    spec_ok = True
    spec_detail = ""
    try:
        from coral.agent.assignments import resolve_agent_specs
        from coral.config import CoralConfig

        cfg = CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "agents": {"binding": binding.name},
            }
        )
        specs = resolve_agent_specs(cfg)
        spec_detail = f"resolved to runtime={specs[0].runtime} model={specs[0].model}"
    except Exception as e:  # noqa: BLE001 - surface any resolution failure to the user
        spec_ok = False
        spec_detail = str(e)
    rows.append(("resolves to AgentSpec", spec_ok, spec_detail))

    # 2. CLI exists on PATH or at the configured command path.
    command = binding.command or default_command_for_runtime(binding.runtime) or ""
    resolved = None
    if command:
        cand = Path(command).expanduser()
        if cand.is_absolute() or "/" in command:
            resolved = str(cand) if cand.exists() else None
        else:
            resolved = shutil.which(command)
    cli_ok = resolved is not None
    rows.append(
        (
            "CLI found",
            cli_ok,
            f"{resolved}" if cli_ok else f"{command!r} not found on PATH",
        )
    )

    # 3. Version command works (best-effort, only if the CLI was found).
    if cli_ok and resolved:
        ver_ok, ver_detail = _try_version(resolved)
        rows.append(("CLI --version", ver_ok, ver_detail))
    else:
        rows.append(("CLI --version", False, "skipped (CLI not found)"))

    # 4. Role file exists, if specified.
    if binding.role_file:
        rf = Path(binding.role_file).expanduser()
        rows.append(
            (
                "role_file exists",
                rf.is_file(),
                str(rf) if rf.is_file() else f"{binding.role_file} not found",
            )
        )

    return rows


def _try_version(command: str) -> tuple[bool, str]:
    for flag in ("--version", "version"):
        try:
            proc = subprocess.run(
                [command, flag],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"could not run {command} {flag}: {e}"
        if proc.returncode == 0:
            out = (proc.stdout or proc.stderr).strip().splitlines()
            return True, out[0] if out else "ok"
    return False, "no working --version flag (auth check deferred to runtime login)"


def _print_doctor(binding: AgentBinding, rows: list[tuple[str, bool, str]]) -> bool:
    all_ok = all(ok for _, ok, _ in rows)
    status = "OK" if all_ok else "PROBLEMS"
    print(f"doctor: {binding.name} ({binding.runtime}) — {status}")
    for label, ok, detail in rows:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {label}: {detail}")
    if not all_ok:
        cmd = binding.command or default_command_for_runtime(binding.runtime) or "<cli>"
        print(
            f"  note: if authentication is the issue, run the runtime-native "
            f"login flow (e.g. `{cmd} login`)."
        )
    return all_ok
