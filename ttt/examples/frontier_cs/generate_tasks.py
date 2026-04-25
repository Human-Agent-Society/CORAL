#!/usr/bin/env python3
"""Generate ttt task configs for all CPU-only Frontier-CS research problems.

Reads from examples/frontier_cs_research/*/task.yaml, filters to needs_gpu=false,
and generates ttt/examples/frontier_cs_tasks/<problem>/task.yaml with shared eval
and per-problem seed directories.

Usage:
    python ttt/examples/frontier_cs/generate_tasks.py

All generated tasks share the same grader (eval/grader.py), litellm_config.yaml,
and opencode.json. Each problem gets its own seed/ with solution.py and statement.md.
"""

import shutil
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
UPSTREAM_DIR = REPO_ROOT / "examples" / "frontier_cs_research"
OUTPUT_DIR = REPO_ROOT / "ttt" / "examples" / "frontier_cs_tasks"
TEMPLATE_DIR = REPO_ROOT / "ttt" / "examples" / "frontier_cs"

# Shared files (same for all problems)
SHARED_EVAL = TEMPLATE_DIR / "eval" / "grader.py"
SHARED_LITELLM = TEMPLATE_DIR / "seed" / "litellm_config.yaml"
SHARED_OPENCODE = TEMPLATE_DIR / "seed" / "opencode.json"

TASK_YAML_TEMPLATE = """\
task:
  name: "Frontier-CS: {display_name} (TTT)"
  description: |
    Solve the '{display_name}' research problem from the Frontier-CS benchmark.

    Read the full problem statement in `statement.md`.
    Write your solution in `solution.py`.

    Your score will be 0-100 based on solution quality.
  tips: |
    - Read statement.md carefully for the exact interface and scoring formula.
    - Evaluation timeout: {timeout}s.
    - Language: {language}.

grader:
  timeout: {timeout}
  direction: maximize
  args:
    problem_name: {problem_name}
    variant_name: "{variant_name}"
    language: {language}
    needs_gpu: false

agents:
  count: 1
  runtime: opencode
  model: sglang/qwen3-4b
  research: false
  max_turns: 200
  gateway:
    enabled: true
    config: "./seed/litellm_config.yaml"
  heartbeat:
    - name: reflect
      every: 5
    - name: diagnose
      every: 5

workspace:
  results_dir: "./results"
  repo_path: "./ttt/examples/frontier_cs_tasks/{dir_name}/seed"

run:
  verbose: false
  ui: false
  session: local
"""


def main():
    cpu_problems = []

    for task_dir in sorted(UPSTREAM_DIR.iterdir()):
        task_yaml = task_dir / "task.yaml"
        if not task_yaml.exists():
            continue

        with open(task_yaml) as f:
            config = yaml.safe_load(f)

        grader_args = config.get("grader", {}).get("args", {})
        if grader_args.get("needs_gpu", True):
            continue

        cpu_problems.append((task_dir, config, grader_args))

    print(f"Found {len(cpu_problems)} CPU-only problems")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for task_dir, config, grader_args in cpu_problems:
        dir_name = task_dir.name
        out_dir = OUTPUT_DIR / dir_name

        # Create directories
        (out_dir / "eval").mkdir(parents=True, exist_ok=True)
        (out_dir / "seed").mkdir(parents=True, exist_ok=True)

        # Copy shared eval
        shutil.copy2(SHARED_EVAL, out_dir / "eval" / "grader.py")

        # Copy shared config files
        shutil.copy2(SHARED_LITELLM, out_dir / "seed" / "litellm_config.yaml")
        shutil.copy2(SHARED_OPENCODE, out_dir / "seed" / "opencode.json")

        # Copy problem-specific seed files
        upstream_seed = task_dir / "seed"
        if upstream_seed.exists():
            for f in upstream_seed.iterdir():
                if f.is_file():
                    shutil.copy2(f, out_dir / "seed" / f.name)

        # Generate task.yaml
        problem_name = grader_args.get("problem_name", "")
        variant_name = grader_args.get("variant_name", "")
        language = grader_args.get("language", "python")
        timeout = config.get("grader", {}).get("timeout", 1800)

        if variant_name:
            display_name = f"{problem_name} ({variant_name})"
        else:
            display_name = problem_name

        task_content = TASK_YAML_TEMPLATE.format(
            display_name=display_name,
            problem_name=problem_name,
            variant_name=variant_name,
            language=language,
            timeout=timeout,
            dir_name=dir_name,
        )

        (out_dir / "task.yaml").write_text(task_content)
        print(f"  ✓ {dir_name}")

    print(f"\nGenerated {len(cpu_problems)} task configs in {OUTPUT_DIR}")
    print(f"\nRun any problem with:")
    print(f"  CORAL_TASK_YAML=ttt/examples/frontier_cs_tasks/<problem>/task.yaml \\")
    print(f"    ./ttt/run_coral_distill.sh")


if __name__ == "__main__":
    main()
