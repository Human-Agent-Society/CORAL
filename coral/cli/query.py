"""Commands: log (attempts), show (attempt), notes, skills, runs, plot."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from coral.cli._helpers import find_coral_dir, read_direction


def cmd_log(args: argparse.Namespace) -> None:
    """List and search attempts (leaderboard).

    Examples:
      coral log                     Top 20 attempts by score
      coral log -n 5                Top 5
      coral log --recent            Sort by time instead of score
      coral log --agent agent-1     Filter by agent
      coral log --search "kernel"   Full-text search
    """
    from coral.hub.attempts import (
        format_leaderboard,
        get_agent_attempts,
        get_leaderboard,
        get_recent,
        search_attempts,
    )

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    direction = read_direction(coral_dir)
    count = getattr(args, "count", None) or 20

    if args.search:
        attempts = search_attempts(str(coral_dir), args.search)
        if attempts:
            print(f"Search results for '{args.search}':")
            print(format_leaderboard(attempts))
        else:
            print(f"No attempts matching '{args.search}'.")
    elif args.agent:
        attempts = get_agent_attempts(str(coral_dir), args.agent)
        if attempts:
            print(f"Attempts by {args.agent}:")
            print(format_leaderboard(attempts))
        else:
            print(f"No attempts by {args.agent}.")
    elif args.recent:
        attempts = get_recent(str(coral_dir), n=count)
        if attempts:
            print(f"Recent {len(attempts)} attempt(s):")
            print(format_leaderboard(attempts))
        else:
            print("No attempts yet.")
    else:
        attempts = get_leaderboard(str(coral_dir), top_n=count, direction=direction)
        if attempts:
            print(f"Leaderboard (top {len(attempts)}):")
            print(format_leaderboard(attempts))
        else:
            print("No attempts yet.")


def cmd_show(args: argparse.Namespace) -> None:
    """Show details of a specific attempt.

    Examples:
      coral show abc123             Show attempt by hash prefix
      coral show <full-hash>        Show attempt by full hash
    """
    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    attempt_file = coral_dir / "public" / "attempts" / f"{args.hash}.json"

    if not attempt_file.exists():
        matches = list((coral_dir / "public" / "attempts").glob(f"{args.hash}*.json"))
        if len(matches) == 1:
            attempt_file = matches[0]
        elif len(matches) > 1:
            print(f"Ambiguous hash prefix '{args.hash}'. Matches:")
            for m in matches:
                print(f"  {m.stem}")
            return
        else:
            print(f"Attempt {args.hash} not found.")
            return

    data = json.loads(attempt_file.read_text())
    print(f"Commit:  {data['commit_hash']}")
    print(f"Agent:   {data['agent_id']}")
    print(f"Title:   {data['title']}")
    print(f"Score:   {data.get('score', '—')}")
    print(f"Status:  {data['status']}")
    print(f"Time:    {data['timestamp']}")
    if data.get("parent_hash"):
        print(f"Parent:  {data['parent_hash']}")
    if data.get("feedback"):
        print(f"Feedback: {data['feedback']}")

    commit = data["commit_hash"]
    git_args = ["git", "show", commit]
    if not getattr(args, "diff", False):
        git_args.insert(2, "--stat")
    result = subprocess.run(
        git_args,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        label = "Diff" if getattr(args, "diff", False) else "Summary"
        print(f"\n--- {label} ---\n{result.stdout}")


def cmd_notes(args: argparse.Namespace) -> None:
    """Browse shared notes.

    Examples:
      coral notes                   List all notes
      coral notes -n 5              Last 5 notes
      coral notes --search "idea"   Search notes
      coral notes --read 3          Read note #3
    """
    from coral.hub.notes import (
        format_notes_list,
        get_recent_notes,
        list_notes,
        read_all_notes,
        read_note,
        search_notes,
    )

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))

    if getattr(args, "history", False):
        from coral.hub.checkpoint import checkpoint_history

        entries = checkpoint_history(str(coral_dir))
        if not entries:
            print("No checkpoint history.")
            return
        print(f"{'HASH':<12} {'DATE':<26} MESSAGE")
        print("-" * 72)
        for e in entries:
            print(f"{e['hash'][:10]}   {e['date']:<26} {e['message']}")
        return

    if getattr(args, "diff", None):
        from coral.hub.checkpoint import checkpoint_diff

        print(checkpoint_diff(str(coral_dir), args.diff))
        return

    if args.read:
        try:
            idx = int(args.read)
            entry = read_note(str(coral_dir), idx)
            if entry:
                print(entry)
            else:
                print(f"Note #{idx} not found.")
        except ValueError:
            print(read_all_notes(str(coral_dir)))
    elif args.search:
        results = search_notes(str(coral_dir), args.search)
        if results:
            print(f"Notes matching '{args.search}':")
            print(format_notes_list(results))
        else:
            print(f"No notes matching '{args.search}'.")
    elif args.recent:
        entries = get_recent_notes(str(coral_dir), n=args.recent)
        print(f"Recent notes ({len(entries)}):")
        print(format_notes_list(entries))
    else:
        entries = list_notes(str(coral_dir))
        print(f"Notes ({len(entries)}):")
        print(format_notes_list(entries))


def cmd_skills(args: argparse.Namespace) -> None:
    """Browse shared skills.

    Examples:
      coral skills                  List all skills
      coral skills --read optim     Show skill by name (or prefix)
    """
    from coral.hub.skills import format_skills_list, list_skills, read_skill

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))

    if args.read:
        skills_dir = coral_dir / "public" / "skills"
        skill_dir = skills_dir / args.read
        if not skill_dir.is_dir():
            matches = [
                d for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith(args.read)
            ]
            if len(matches) == 1:
                skill_dir = matches[0]
            elif len(matches) > 1:
                print(f"Ambiguous name '{args.read}'. Matches:")
                for m in matches:
                    print(f"  {m.name}")
                return
            else:
                print(f"Skill '{args.read}' not found.")
                return
        info = read_skill(skill_dir)
        print(info["content"])
        if info["files"]:
            print(f"\nFiles: {', '.join(info['files'])}")
    else:
        skills = list_skills(str(coral_dir))
        print(f"Skills ({len(skills)}):")
        print(format_skills_list(skills))


def _find_results_dir() -> Path:
    """Walk up from cwd to find the results/ directory."""
    current = Path.cwd()
    while True:
        candidate = current / "results"
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    print("No results/ directory found.", file=sys.stderr)
    sys.exit(1)


def _relative_time(timestamp_str: str) -> str:
    """Convert a run timestamp like '2026-03-11_163000' to a relative time string."""
    from datetime import datetime

    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return timestamp_str
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h}h ago"
    d = seconds // 86400
    return f"{d}d ago"


def _collect_runs(results_dir: Path) -> list[dict]:
    """Scan results/ and collect metadata for all runs."""
    runs = []
    for task_dir in sorted(results_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task_name = task_dir.name

        latest_link = task_dir / "latest"
        latest_resolved = None
        if latest_link.is_symlink():
            try:
                latest_resolved = latest_link.resolve()
            except OSError:
                pass

        for run_dir in sorted(task_dir.iterdir()):
            if not run_dir.is_dir() or run_dir.is_symlink():
                continue
            coral_dir = run_dir / ".coral"
            if not coral_dir.is_dir():
                continue

            pid_file = coral_dir / "public" / "manager.pid"
            status = "stopped"
            manager_pid = None
            if pid_file.exists():
                try:
                    manager_pid = int(pid_file.read_text().strip())
                    os.kill(manager_pid, 0)
                    status = "running"
                except (ProcessLookupError, ValueError):
                    status = "stopped"

            logs_dir = coral_dir / "public" / "logs"
            agent_names: set[str] = set()
            if logs_dir.exists():
                for lf in logs_dir.glob("*.log"):
                    parts = lf.stem.rsplit(".", 1)
                    agent_names.add(parts[0] if len(parts) == 2 else lf.stem)

            # Load config for model/runtime/grader/direction info
            config_file = coral_dir / "config.yaml"
            model = ""
            runtime = ""
            direction = "maximize"
            if config_file.exists():
                try:
                    import yaml

                    cfg = yaml.safe_load(config_file.read_text()) or {}
                    agents_cfg = cfg.get("agents", {})
                    model = agents_cfg.get("model", "")
                    runtime = agents_cfg.get("runtime", "")
                    grader_cfg = cfg.get("grader", {})
                    direction = grader_cfg.get("direction", "maximize")
                except Exception:
                    pass

            attempts_dir = coral_dir / "public" / "attempts"
            attempt_count = 0
            best_score = None
            if attempts_dir.exists():
                for af in attempts_dir.glob("*.json"):
                    try:
                        adata = json.loads(af.read_text())
                        attempt_count += 1
                        s = adata.get("score")
                        if s is not None:
                            if best_score is None:
                                best_score = s
                            elif direction == "maximize" and s > best_score:
                                best_score = s
                            elif direction == "minimize" and s < best_score:
                                best_score = s
                    except (json.JSONDecodeError, OSError):
                        attempt_count += 1

            is_latest = latest_resolved is not None and (
                latest_resolved == run_dir.resolve()
            )

            runs.append(
                {
                    "task": task_name,
                    "run": run_dir.name,
                    "status": status,
                    "pid": manager_pid,
                    "agents": len(agent_names),
                    "attempts": attempt_count,
                    "best": best_score,
                    "model": model,
                    "runtime": runtime,
                    "latest": is_latest,
                    "path": str(run_dir),
                }
            )
    return runs


def cmd_runs(args: argparse.Namespace) -> None:
    """List CORAL runs.

    Examples:
      coral runs                    Active runs only
      coral runs --all              Include stopped runs
      coral runs --task my-task     Filter by task
      coral runs -n 5              Show at most 5 runs
    """
    results_dir = _find_results_dir()
    show_all = getattr(args, "all", False)
    task_filter = getattr(args, "task", None)
    count = getattr(args, "count", None) or 20
    verbose = getattr(args, "verbose", False)

    runs = _collect_runs(results_dir)

    # Filter by task name
    if task_filter:
        runs = [r for r in runs if task_filter in r["task"]]

    # Filter: active only unless --all
    if not show_all:
        runs = [r for r in runs if r["status"] == "running"]

    # Sort: running first, then by run timestamp descending (most recent first)
    runs.sort(key=lambda r: (r["status"] != "running", r["run"]), reverse=False)
    # Reverse the run name sort within each group for most-recent-first
    running = [r for r in runs if r["status"] == "running"]
    stopped = [r for r in runs if r["status"] != "running"]
    running.sort(key=lambda r: r["run"], reverse=True)
    stopped.sort(key=lambda r: r["run"], reverse=True)
    runs = running + stopped

    # Apply limit
    total = len(runs)
    runs = runs[:count]

    if not runs:
        if show_all:
            print("No runs found.")
        else:
            print("No active runs. Use --all to see stopped runs.")
        return

    # Compute column widths from data
    tw = max(len("TASK"), max((len(r["task"]) for r in runs), default=4)) + 2
    rw = max(len("RUN"), max((len(r["run"]) + 2 for r in runs), default=3)) + 2  # +2 for " *"
    sw = max(len("STATUS"), 20)
    mw = max(len("MODEL"), max((len(r["model"]) for r in runs), default=5)) + 2
    rtw = max(len("RUNTIME"), max((len(r["runtime"]) for r in runs), default=7)) + 2

    header = (
        f"{'TASK':<{tw}}{'RUN':<{rw}}{'STATUS':<{sw}}"
        f"{'AGENTS':>8}{'EVALS':>8}{'BEST':>10}"
        f"  {'MODEL':<{mw}}{'RUNTIME':<{rtw}}"
    )
    if verbose:
        header += "  PATH"
    print(header)
    print("-" * len(header))

    for r in runs:
        latest_marker = " *" if r["latest"] else ""
        run_col = f"{r['run']}{latest_marker}"
        if r["status"] == "running":
            status_str = f"running (PID {r['pid']})" if r["pid"] else "running"
        else:
            status_str = f"stopped {_relative_time(r['run'])}"

        best_str = f"{r['best']:.4f}" if r["best"] is not None else "-"
        line = (
            f"{r['task']:<{tw}}{run_col:<{rw}}{status_str:<{sw}}"
            f"{r['agents']:>8}{r['attempts']:>8}{best_str:>10}"
            f"  {r['model']:<{mw}}{r['runtime']:<{rtw}}"
        )
        if verbose:
            line += f"  {r['path']}"
        print(line)

    # Summary
    running_count = sum(1 for r in runs if r["status"] == "running")
    print()
    summary = f"{total} run(s)"
    if not show_all:
        summary += " active"
    elif running_count:
        summary += f", {running_count} running"
    if total > count:
        summary += f" (showing {count})"
    summary += "  (* = latest)"
    print(summary)
