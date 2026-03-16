"""Commands: init, validate (formerly test-eval)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> None:
    """Create a new task directory.

    Examples:
      coral init my-task            Scaffold at ./my-task/
      coral init my-task --name "My Task"
    """
    task_path = Path(args.path).resolve()
    task_name = args.name or task_path.name

    if task_path.exists() and any(task_path.iterdir()):
        print(f"Error: {task_path} already exists and is not empty.", file=sys.stderr)
        sys.exit(1)

    task_path.mkdir(parents=True, exist_ok=True)
    (task_path / "seed").mkdir()
    (task_path / "eval").mkdir()

    task_yaml = task_path / "task.yaml"
    task_yaml.write_text(
        f"task:\n"
        f'  name: "{task_name}"\n'
        f"  description: |\n"
        f"    Describe your task here.\n"
        f"  files: []\n"
        f"\n"
        f"grader:\n"
        f"  timeout: 300\n"
        f"  direction: maximize\n"
        f"\n"
        f"agents:\n"
        f"  count: 1\n"
    )

    grader_py = task_path / "eval" / "grader.py"
    grader_py.write_text(
        "from coral.grader import TaskGrader\n"
        "\n"
        "\n"
        "class Grader(TaskGrader):\n"
        '    """Evaluate agent submissions."""\n'
        "\n"
        "    def evaluate(self) -> float:\n"
        "        # self.codebase_path — path to agent's worktree\n"
        "        # self.private_dir   — path to .coral/private/\n"
        "        # self.args          — dict from config.grader.args\n"
        "        #\n"
        "        # Return a float score, or use self.score(value, explanation)\n"
        "        # or self.fail(reason) for richer feedback.\n"
        "        return 0.0\n"
    )

    print(f"Created task at {task_path}/")
    print("  task.yaml       — configure your task")
    print("  eval/grader.py  — implement your grader")
    print("  seed/           — add starting code (optional)")
    print(f"\nNext: edit eval/grader.py, then run: coral validate {task_path}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Test your grader against seed code.

    Examples:
      coral validate my-task        Dry-run the grader in my-task/
    """
    import shutil
    import tempfile

    from coral.config import CoralConfig
    from coral.cli.validation import validate_task

    task_dir = Path(args.path).resolve()

    errors = validate_task(task_dir)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print("Validation: OK")

    config = CoralConfig.from_yaml(task_dir / "task.yaml")

    with tempfile.TemporaryDirectory(prefix="coral_test_eval_") as tmpdir:
        tmpdir = Path(tmpdir)
        workspace = tmpdir / "workspace"
        workspace.mkdir()

        seed_dir = task_dir / "seed"
        if seed_dir.is_dir() and any(seed_dir.iterdir()):
            for item in seed_dir.iterdir():
                if item.name == "__pycache__":
                    continue
                dst = workspace / item.name
                if item.is_dir():
                    shutil.copytree(item, dst)
                else:
                    shutil.copy2(item, dst)
            print(f"Seed: copied {seed_dir.name}/ into workspace")
        else:
            print("Warning: No seed/ directory — grader will run against an empty workspace.")
            print("  This is fine if your task expects agents to build from scratch.")

        coral_dir = tmpdir / ".coral"
        private_dir = coral_dir / "private"
        private_dir.mkdir(parents=True)
        eval_src = task_dir / "eval"
        if eval_src.is_dir():
            shutil.copytree(eval_src, private_dir / "eval")

        for private_path_str in config.grader.private:
            src = Path(private_path_str)
            if not src.is_absolute():
                src = (task_dir / src).resolve()
            if src.exists():
                dst = private_dir / src.name
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        from coral.grader.loader import load_grader
        from coral.types import Task

        try:
            grader = load_grader(config, coral_dir)
        except Exception as e:
            print(f"Error loading grader: {e}", file=sys.stderr)
            sys.exit(1)

        task = Task(
            id=config.task.name,
            name=config.task.name,
            description=config.task.description,
        )

        print(
            f"\nRunning grader against {'seed code' if seed_dir.is_dir() else 'empty workspace'}..."
        )
        import asyncio

        try:
            result = asyncio.run(grader.grade(str(workspace), [task]))
            score = result.aggregated
            print(f"\n{'=' * 50}")
            print(f"Score: {score}")
            if result.scores:
                for name, s in result.scores.items():
                    if s.explanation:
                        print(f"  {name}: {s.explanation}")
            print(f"{'=' * 50}")
        except Exception as e:
            print(f"\nGrader crashed: {e}", file=sys.stderr)
            sys.exit(1)
