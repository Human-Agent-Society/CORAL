"""Commands: eval, revert, diff, checkout."""

from __future__ import annotations

import argparse
import subprocess
import sys

from coral.cli._helpers import find_coral_dir, read_agent_id


def cmd_eval(args: argparse.Namespace) -> None:
    """Stage changes, commit, and run evaluation."""
    from coral.hooks.post_commit import run_eval

    agent_id = args.agent or read_agent_id()

    try:
        attempt = run_eval(
            message=args.message,
            agent_id=agent_id,
            workdir=args.workdir or ".",
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    score_str = f"{attempt.score:.10f}" if attempt.score is not None else "FAILED"
    eval_count = getattr(attempt, "_eval_count", None)
    count_str = f" (#{eval_count})" if eval_count else ""
    print(f"\n{'=' * 50}")
    print(f"CORAL Eval{count_str}: {score_str}")
    print(f"Commit:  {attempt.commit_hash[:12]}")
    print(f"Status:  {attempt.status}")
    if attempt.feedback:
        print(f"Feedback: {attempt.feedback}")
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
