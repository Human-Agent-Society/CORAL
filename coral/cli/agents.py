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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coral.agent.registry import (
    default_command_for_runtime,
    default_model_for_runtime,
    detect_available_runtimes,
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
    """Dispatch `coral setup <subcommand>`.

    With no subcommand, scan PATH for available agent runtime CLIs and, in an
    interactive terminal, offer a numbered selection wizard for creating
    bindings. One runtime can produce multiple bindings (e.g. ``claude-opus``
    and ``claude-sonnet`` both bound to ``claude_code``) via an "add another?"
    prompt after each successful creation. With ``--non-interactive`` the
    detection report is printed and the command exits without prompting.
    """
    sub = getattr(args, "setup_command", None)
    if sub == "agent":
        _setup_agent(args)
    else:
        _setup_detect(args)


def _setup_detect(args: argparse.Namespace) -> None:
    """Scan PATH for agent CLIs and (interactively) offer bindings.

    A single runtime can carry multiple bindings (e.g. ``claude-opus`` and
    ``claude-sonnet`` both pointing at ``claude_code``). The selection list
    therefore always shows every detected runtime — bound or not — and after
    each successful binding we ask whether to create another for the same
    runtime.
    """
    rows = detect_available_runtimes()
    found = [r for r in rows if r["resolved"]]

    path = _store_path(args)
    store = load_store(path)
    bind_count: dict[str, int] = {}
    for b in store.bindings.values():
        bind_count[b.runtime] = bind_count.get(b.runtime, 0) + 1

    print(f"Scanning PATH for agent runtimes ({store.path}):\n")
    name_w = max((len(r["runtime"]) for r in rows), default=8)
    cmd_w = max((len(r["command"]) for r in rows), default=8)
    for r in rows:
        mark = "✓" if r["resolved"] else " "
        status = r["resolved"] or "not found"
        existing = bind_count.get(r["runtime"], 0)
        suffix = f"  ({existing} binding{'s' if existing != 1 else ''})" if existing else ""
        cmd = r["command"] or "-"
        print(f"  {mark} {r['runtime']:<{name_w}}  {cmd:<{cmd_w}}  {status}{suffix}")
    print()

    if not found:
        print("No agent CLIs found on PATH.")
        print(
            "Install one of the supported runtimes "
            "(claude, codex, cursor-agent, opencode, kiro-cli, pi) and re-run."
        )
        print(
            "For a custom runtime, use: "
            "coral setup agent --runtime 'module.path:ClassName' --name <NAME>"
        )
        return

    interactive = not getattr(args, "non_interactive", False) and sys.stdin.isatty()

    if not interactive:
        print(f"{len(found)} runtime(s) detected, {sum(bind_count.values())} binding(s) defined.")
        names = ", ".join(r["runtime"] for r in found)
        print(
            "Create bindings interactively: `coral setup` (in a TTY) "
            f"or `coral setup agent --name <NAME> --runtime <{names}>`."
        )
        return

    print(f"{len(found)} detected runtime(s):\n")
    num_w = len(str(len(found)))
    rt_w = max(len(r["runtime"]) for r in found)
    for idx, r in enumerate(found, start=1):
        existing = bind_count.get(r["runtime"], 0)
        suffix = (
            f"  [{existing} existing binding{'s' if existing != 1 else ''}]" if existing else ""
        )
        print(
            f"  [{idx:>{num_w}}] {r['runtime']:<{rt_w}}  ({r['command']}"
            f", model {r['model'] or '-'}){suffix}"
        )
    print()

    selected = _prompt_selection(len(found))
    if not selected:
        print("No bindings created.")
        return

    print()
    created = 0
    for idx in selected:
        r = found[idx - 1]
        runtime = r["runtime"]
        while True:
            print(f"Setting up {runtime}:")
            if not _create_one_binding(r, store):
                break
            created += 1
            more = _prompt(f"Add another binding for {runtime}? [y/N]", default="n").strip().lower()
            if more not in ("y", "yes"):
                break

    if created:
        written = save_store(store, path)
        print(f"Saved {created} binding(s) to {written}.")
        print("Inspect with `coral agents list`, validate with `coral agents doctor`.")
    else:
        print("No bindings created.")


def _create_one_binding(row: dict, store) -> bool:  # noqa: ANN001 - BindingStore forward ref
    """Prompt for binding name + model, mutate ``store``. Return True on success."""
    runtime = row["runtime"]
    default_name = runtime.replace("_", "-")
    suggest = default_name
    i = 2
    while suggest in store.bindings:
        suggest = f"{default_name}-{i}"
        i += 1
    name = _prompt("  Binding name", default=suggest).strip()
    if not name:
        print(f"  skipping {runtime} — empty binding name")
        print()
        return False
    if name in store.bindings:
        print(f"  skipping — a binding named {name!r} already exists")
        print()
        return False
    model = _prompt("  Model", default=row["model"] or "").strip()
    role_file = _prompt(
        "  Role seed file path (optional, e.g. ~/roles/generalist.md, Enter to skip)",
        default="",
    ).strip()
    if role_file and not Path(role_file).expanduser().is_file():
        print(f"  note: no file at {role_file} yet — `coral agents doctor` will flag this.")

    binding = AgentBinding(
        name=name,
        runtime=runtime,
        command=row["command"],
        model=model,
        runtime_options={},
        role_file=role_file,
    )
    store.bindings[name] = binding
    if store.default is None:
        store.default = name
    print(f"  ✓ created binding {name!r}")
    print()
    return True


def _parse_selection(raw: str, count: int) -> list[int] | None:
    """Parse a selection string like '1,3', '1-3', or 'all' into 1-based indices.

    Returns ``[]`` for empty / skip input, a sorted list of indices for a valid
    selection, or ``None`` when the input is malformed (caller should re-prompt).
    """
    s = raw.strip().lower()
    if not s or s in ("q", "quit", "n", "no", "none", "skip"):
        return []
    if s == "all":
        return list(range(1, count + 1))
    selected: set[int] = set()
    for tok in s.replace(",", " ").split():
        if "-" in tok:
            lo, _, hi = tok.partition("-")
            try:
                start, end = int(lo), int(hi)
            except ValueError:
                return None
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                if not 1 <= i <= count:
                    return None
                selected.add(i)
        else:
            try:
                i = int(tok)
            except ValueError:
                return None
            if not 1 <= i <= count:
                return None
            selected.add(i)
    return sorted(selected)


def _prompt_selection(count: int, attempts: int = 3) -> list[int]:
    """Prompt for a numbered selection; re-prompt on malformed input."""
    label = f"Select runtimes to bind [1-{count}, comma/space-separated, 'all', or Enter to skip]"
    for _ in range(attempts):
        raw = _prompt(label, default="").strip()
        picked = _parse_selection(raw, count)
        if picked is not None:
            return picked
        print(f"  '{raw}' is not a valid selection. Use e.g. '1', '1,3', '1-3', or 'all'.")
    print("  too many invalid attempts — skipping.")
    return []


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
            "Role seed file path (optional, e.g. ~/roles/generalist.md)",
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
        print("Create one with `coral setup` or `coral setup agent`.")
        return
    names = sorted(store.bindings)
    num_w = len(str(len(names)))
    print(f"Agent bindings ({store.path}):\n")
    for idx, name in enumerate(names, start=1):
        b = store.bindings[name]
        marker = " (default)" if store.default == name else ""
        model = b.model or default_model_for_runtime(b.runtime) or "?"
        print(f"  [{idx:>{num_w}}] {name}{marker}")
        print(f"      runtime: {b.runtime}    model: {model}    command: {b.command or '-'}")
        if b.role_file:
            print(f"      role_file: {b.role_file}")
        if b.runtime_options:
            print(f"      runtime_options: {b.runtime_options}")
    print()
    print("Remove with `coral agents remove` (interactive) or `coral agents remove <name>`.")


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
    if not store.bindings:
        print(f"No agent bindings defined ({store.path}).")
        return

    names = getattr(args, "names", None) or []

    if not names:
        names = _interactive_remove_picker(store)
        if not names:
            return

    # Pre-validate: any unknown name aborts the whole removal.
    unknown = [n for n in names if n not in store.bindings]
    if unknown:
        print(
            f"Error: no such binding(s) in {store.path}: {', '.join(repr(n) for n in unknown)}",
            file=sys.stderr,
        )
        sys.exit(1)

    for n in names:
        del store.bindings[n]
        print(f"  ✓ removed '{n}'")
    if store.default in (None, *names):
        store.default = next(iter(sorted(store.bindings)), None)
        if store.default:
            print(f"New default: {store.default}")
    save_store(store, path)


def _interactive_remove_picker(store) -> list[str]:  # noqa: ANN001 - BindingStore forward ref
    """Print a numbered list of bindings and prompt the user to pick names to remove."""
    names = sorted(store.bindings)
    num_w = len(str(len(names)))
    print(f"Agent bindings ({store.path}):\n")
    for idx, n in enumerate(names, start=1):
        marker = " (default)" if store.default == n else ""
        b = store.bindings[n]
        print(f"  [{idx:>{num_w}}] {n}{marker}    ({b.runtime}, model {b.model or '-'})")
    print()

    selected = _prompt_selection(len(names))
    if not selected:
        print("No bindings removed.")
        return []

    picked = [names[i - 1] for i in selected]
    label = ", ".join(picked)
    confirm = (
        _prompt(f"Remove {len(picked)} binding(s): {label}? [y/N]", default="n").strip().lower()
    )
    if confirm not in ("y", "yes"):
        print("No bindings removed.")
        return []
    return picked


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

    live = not getattr(args, "no_live", False)
    timeout = float(getattr(args, "timeout", None) or 30.0)

    any_fail = False
    for binding in targets:
        issues = _validate_binding(binding, live=live, ping_timeout=timeout)
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


def _validate_binding(
    binding: AgentBinding,
    *,
    live: bool = False,
    ping_timeout: float = 30.0,
) -> list[tuple[str, bool, str]]:
    """Run validation checks. Returns (label, ok, detail) rows.

    With ``live=False`` (default) only lightweight metadata checks run — fast
    and free, no LLM round-trip. The ``coral setup agent`` auto-doctor pass
    uses this mode.

    With ``live=True``, after the metadata checks pass, this also spawns the
    runtime CLI with a one-word prompt and waits ``ping_timeout`` seconds for
    a reply. Costs one LLM round-trip per call. ``coral agents doctor`` uses
    this mode by default; pass ``--no-live`` to skip.

    Checks never store or transmit credentials.
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

    # 5. Live hello-ping (opt-in). Skipped silently when the CLI was missing —
    #    the CLI-found row already flagged it.
    if live and cli_ok and resolved:
        model = binding.model or default_model_for_runtime(binding.runtime) or ""
        ok, detail = _try_ping(binding.runtime, resolved, model, ping_timeout)
        rows.append(("live ping", ok, detail))

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


# A short, deterministic prompt that should produce minimal tokens across
# every runtime. Kept identical for all runtimes so logs from different
# runtimes are directly comparable.
_PING_PROMPT = "Reply with just the word: ok"


# Per-runtime non-interactive invocation. None ⇒ runtime has no clean
# non-interactive mode; ping is skipped with "not implemented".
_RUNTIME_PING_CMD: dict[str, Callable[[str, str], list[str]]] = {
    "claude_code": lambda cmd, model: [cmd, "-p", _PING_PROMPT, "--model", model],
    "codex": lambda cmd, _model: [cmd, "exec", _PING_PROMPT],
    "cursor_agent": lambda cmd, _model: [cmd, "--print", _PING_PROMPT],
    "opencode": lambda cmd, model: [cmd, "run", "--model", model, _PING_PROMPT],
    "pi": lambda cmd, _model: [cmd, "--print", _PING_PROMPT],
    # kiro intentionally absent — no documented non-interactive mode.
}


def _try_ping(runtime: str, command: str, model: str, timeout: float) -> tuple[bool, str]:
    """Spawn the runtime CLI with a one-word prompt; return (ok, detail).

    Success criterion: exit code 0 AND non-empty stdout within ``timeout`` seconds.
    Failure modes (each surfaced in ``detail``): unsupported runtime, missing
    command/model, timeout, non-zero exit, empty stdout.
    """
    builder = _RUNTIME_PING_CMD.get(runtime)
    if builder is None:
        return False, f"live ping not implemented for runtime {runtime!r}"
    if not command:
        return False, "no CLI command resolved"
    # Some runtimes embed the model in the command; missing model is fatal there.
    needs_model = runtime in ("claude_code", "opencode")
    if needs_model and not model:
        return False, "no model configured for this binding"

    argv = builder(command, model)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout:g}s — CLI did not reply"
    except OSError as e:
        return False, f"could not invoke {command}: {e}"
    elapsed = time.monotonic() - t0

    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        snippet = err[0] if err else "no stderr"
        return False, f"exit {proc.returncode} in {elapsed:.1f}s: {snippet[:120]}"
    if not out:
        return False, f"empty stdout (exit 0 in {elapsed:.1f}s)"

    first_line = out.splitlines()[0]
    truncated = first_line if len(first_line) <= 60 else first_line[:60] + "…"
    return True, f"reply received in {elapsed:.1f}s ({truncated!r})"


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
