"""Commands: eval, wait, revert, diff, checkout."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from coral.cli._helpers import find_coral_dir, read_agent_id

# Poll cadence used by `coral wait` while blocking on the attempt file.
_WAIT_POLL_INTERVAL_SEC = 0.2


def cmd_eval(args: argparse.Namespace) -> None:
    """Stage changes, commit, and submit evaluation (blocking by default)."""
    from coral.hooks.post_commit import submit_eval

    agent_id = args.agent or read_agent_id()
    wait = getattr(args, "wait", True)
    timeout = getattr(args, "timeout", None)

    try:
        attempt = submit_eval(
            message=args.message,
            agent_id=agent_id,
            workdir=args.workdir or ".",
            wait=wait,
            poll_timeout=timeout,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError as e:
        print(
            f"\n{'=' * 50}\n"
            f"CORAL Eval: STILL PENDING\n"
            f"{e}\n"
            f"Use `coral wait <hash>` to keep waiting, or check `coral log`.\n"
            f"{'=' * 50}\n",
            file=sys.stderr,
        )
        sys.exit(2)

    _print_attempt_result(attempt, header="CORAL Eval")


def cmd_wait(args: argparse.Namespace) -> None:
    """Block until a previously submitted attempt is finalized by the grader."""
    from coral.config import CoralConfig
    from coral.hub.attempts import read_attempt, read_eval_count

    # Prefer the workdir's .coral_dir breadcrumb (agent-local); otherwise
    # fall back to find_coral_dir's search logic.
    workdir = Path(args.workdir or ".").resolve()
    coral_dir: Path | None = None
    breadcrumb = workdir / ".coral_dir"
    if breadcrumb.exists():
        try:
            coral_dir = Path(breadcrumb.read_text().strip()).resolve()
        except OSError:
            coral_dir = None
    if coral_dir is None:
        try:
            coral_dir = find_coral_dir(
                getattr(args, "task", None), getattr(args, "run", None),
            )
        except Exception as e:
            print(f"Error: Could not locate .coral directory: {e}", file=sys.stderr)
            sys.exit(1)

    # Resolve partial hash against the attempts directory.
    target = args.hash
    attempts_dir = coral_dir / "public" / "attempts"
    if attempts_dir.exists() and len(target) < 40:
        matches = list(attempts_dir.glob(f"{target}*.json"))
        if len(matches) == 1:
            target = matches[0].stem
        elif len(matches) > 1:
            print(f"Ambiguous hash prefix '{target}'. Matches:", file=sys.stderr)
            for m in matches:
                print(f"  {m.stem}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error: No attempt matches '{target}'.", file=sys.stderr)
            sys.exit(1)

    # Derive timeout.
    timeout = args.timeout
    if timeout is None:
        try:
            config = CoralConfig.from_yaml(coral_dir / "config.yaml")
            grader_timeout = config.grader.timeout if config.grader.timeout > 0 else 0
            timeout = max(grader_timeout * 2 + 60, 300) if grader_timeout else 3600
        except Exception:
            timeout = 3600

    deadline = time.monotonic() + timeout
    attempt = None
    while time.monotonic() < deadline:
        attempt = read_attempt(coral_dir, target)
        if attempt is not None and attempt.status != "pending":
            try:
                attempt._eval_count = read_eval_count(coral_dir)  # type: ignore[attr-defined]
            except Exception:
                pass
            _print_attempt_result(attempt, header="CORAL Wait")
            return
        time.sleep(_WAIT_POLL_INTERVAL_SEC)

    if attempt is None:
        print(f"Error: No attempt found for '{target}'.", file=sys.stderr)
        sys.exit(1)
    print(
        f"\n{'=' * 50}\n"
        f"CORAL Wait: STILL PENDING\n"
        f"Attempt {target[:12]} not graded within {timeout:.0f}s.\n"
        f"Re-run `coral wait` to keep waiting, or check `coral status`.\n"
        f"{'=' * 50}\n",
        file=sys.stderr,
    )
    sys.exit(2)


def _print_attempt_result(attempt, header: str) -> None:
    """Shared formatter for `coral eval` and `coral wait` output."""
    score_str = (
        f"{attempt.score:.10f}" if attempt.score is not None else "FAILED"
    )
    if attempt.status == "pending":
        score_str = "PENDING"
    eval_count = getattr(attempt, "_eval_count", None)
    count_str = f" (#{eval_count})" if eval_count else ""
    print(f"\n{'=' * 50}")
    print(f"{header}{count_str}: {score_str}")
    print(f"Commit:  {attempt.commit_hash[:12]}")
    print(f"Status:  {attempt.status}")
    if attempt.feedback:
        print(f"Feedback: {attempt.feedback}")
    if attempt.status == "pending":
        print(
            "Tip: grader is still working. "
            f"Run `coral wait {attempt.commit_hash[:12]}` to block on the result."
        )
    print(f"{'=' * 50}\n")


def cmd_revert(args: argparse.Namespace) -> None:
    """Revert to the last commit (undo uncommitted changes and last commit)."""
    workdir = args.workdir or "."

    result = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    if result.returncode != 0:
        print("Error: No commits to revert.", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    if result.returncode != 0:
        print(f"Error: git reset failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def cmd_checkout(args: argparse.Namespace) -> None:
    """Checkout a previous attempt's code by commit hash."""
    workdir = args.workdir or "."
    target = args.hash

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    attempts_dir = coral_dir / "public" / "attempts"
    if attempts_dir.exists():
        matches = list(attempts_dir.glob(f"{target}*.json"))
        if len(matches) == 1:
            target = matches[0].stem
        elif len(matches) > 1:
            print(f"Ambiguous hash prefix '{target}'. Matches:")
            for m in matches:
                print(f"  {m.stem}")
            return

    result = subprocess.run(
        ["git", "cat-file", "-t", target],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    if result.returncode != 0:
        print(f"Error: Commit '{target}' not found.", file=sys.stderr)
        sys.exit(1)

    log_result = subprocess.run(
        ["git", "log", "--oneline", "-1", target],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    print(f"Checking out: {log_result.stdout.strip()}")

    result = subprocess.run(
        ["git", "reset", "--hard", target],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    if result.returncode != 0:
        print(f"Error: git reset failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def cmd_diff(args: argparse.Namespace) -> None:
    """Show current uncommitted changes."""
    workdir = args.workdir or "."

    result = subprocess.run(
        ["git", "diff", "HEAD"],
        capture_output=True,
        text=True,
        cwd=workdir,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            cwd=workdir,
        )

    if result.stdout:
        print(result.stdout)
    else:
        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=workdir,
        )
        if status.stdout:
            print(status.stdout)
        else:
            print("No changes.")
