"""One-shot codemod: migrate legacy eval/grader.py tasks to packaged graders.

For every task under examples/ that has eval/grader.py and no grader.entrypoint:

  - frontier_cs_algo/* and frontier_cs_research/* share one grader each
    (all 172 / 127 copies are byte-identical). Following the frontier_eng
    convention, the canonical package lives at examples/<group>/_grader/ and
    each task gets a copy at <task>/grader/ so task dirs stay self-contained.
  - every other task gets its own <task>/grader/ package built from its
    eval/grader.py.

In all cases:
  - task.yaml gains grader.entrypoint + grader.setup (inserted textually right
    after the `grader:` line so comments/formatting elsewhere are preserved).
  - eval/grader.py is deleted; other eval/ assets (test data, answer keys,
    helper modules) stay — they are still copied to .coral/private/eval/ and
    read via TaskGrader.read_eval()/private_dir.

Idempotent: tasks whose task.yaml already sets entrypoint are skipped.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"

FRONTIER_CS_INSTALL = "uv pip install git+https://github.com/FrontierCS/Frontier-CS.git"

SHARED_GROUPS = {
    "frontier_cs_algo": {
        "pkg": "frontier_cs_algo_grader",
        "description": "CORAL grader for Frontier-CS algorithmic problems (shared by all variants).",
        "extra_setup": [FRONTIER_CS_INSTALL],
    },
    "frontier_cs_research": {
        "pkg": "frontier_cs_research_grader",
        "description": "CORAL grader for Frontier-CS research problems (shared by all variants).",
        "extra_setup": [FRONTIER_CS_INSTALL],
    },
}

# Legacy graders ran in-process inside CORAL's host venv, so any third-party
# packages their inline eval scripts (or in-process-imported eval/seed modules)
# needed were implicitly satisfied by whatever the host had installed. The
# grader venv is isolated, so those deps must be declared explicitly on the
# grader package. (Tasks whose seed ships a pyproject.toml — e.g. math/* — run
# agent code via `uv run --project <codebase>` instead and need nothing here.)
TASK_DEPS = {
    "circle_packing": ["numpy", "scipy"],
    "mnist": ["numpy", "scikit-learn"],
    "spaceship_titanic": ["numpy", "pandas", "scikit-learn"],
    "stanford_covid_vaccine": ["numpy", "pandas", "scikit-learn"],
    "ADRS/cloudcast": ["networkx", "pandas"],
    "ADRS/llm_sql": ["networkx", "pandas"],
    "ADRS/eplb": ["torch"],
    "ADRS/prism": ["numpy"],
    "ADRS/txn_scheduling": ["numpy"],
}

PYPROJECT_TEMPLATE = """\
[project]
name = "{dist_name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.11"
dependencies = [
    "coral",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg}"]
"""

INIT_TEMPLATE = '''\
"""{title} (entrypoint: {pkg}.grader:Grader)."""

from .grader import Grader

__all__ = ["Grader"]
'''


def find_legacy_tasks() -> list[Path]:
    tasks = []
    for grader_py in sorted(EXAMPLES.rglob("eval/grader.py")):
        task_dir = grader_py.parent.parent
        task_yaml = task_dir / "task.yaml"
        if not task_yaml.exists():
            print(f"SKIP (no task.yaml): {task_dir}", file=sys.stderr)
            continue
        if "entrypoint:" in task_yaml.read_text():
            print(f"SKIP (already entrypoint): {task_dir}", file=sys.stderr)
            continue
        tasks.append(task_dir)
    return tasks


def write_package(
    grader_dir: Path,
    pkg: str,
    description: str,
    grader_source: str,
    extra_deps: list[str] | None = None,
) -> None:
    src_pkg = grader_dir / "src" / pkg
    src_pkg.mkdir(parents=True, exist_ok=True)
    dist_name = pkg.replace("_", "-")
    pyproject = PYPROJECT_TEMPLATE.format(dist_name=dist_name, description=description, pkg=pkg)
    extra = "".join(f'    "{d}",\n' for d in extra_deps or [])
    pyproject = pyproject.replace('    "coral",\n', '    "coral",\n' + extra)
    (grader_dir / "pyproject.toml").write_text(pyproject)
    (src_pkg / "__init__.py").write_text(
        INIT_TEMPLATE.format(title=description.rstrip("."), pkg=pkg)
    )
    (src_pkg / "grader.py").write_text(grader_source)


def patch_task_yaml(task_yaml: Path, pkg: str, extra_setup: list[str]) -> None:
    lines = task_yaml.read_text().splitlines(keepends=True)
    out, inserted = [], False
    setup_lines = ['    - "uv pip install -e ./grader"\n'] + [
        f'    - "{cmd}"\n' for cmd in extra_setup
    ]
    for line in lines:
        out.append(line)
        if not inserted and line.rstrip("\n") == "grader:":
            out.append(f'  entrypoint: "{pkg}.grader:Grader"\n')
            out.append("  setup:\n")
            out.extend(setup_lines)
            inserted = True
    if not inserted:
        raise RuntimeError(f"No `grader:` block found in {task_yaml}")
    task_yaml.write_text("".join(out))


def remove_legacy_grader(task_dir: Path) -> None:
    grader_py = task_dir / "eval" / "grader.py"
    grader_py.unlink()
    eval_dir = task_dir / "eval"
    leftovers = [p for p in eval_dir.rglob("*") if p.name != "__pycache__"]
    if not leftovers:
        shutil.rmtree(eval_dir)


def slug_for(task_dir: Path) -> str:
    slug = task_dir.name.lower().replace("-", "_").replace(".", "_")
    if slug[0].isdigit():
        slug = f"{task_dir.parent.name.lower()}_{slug}"
    return f"{slug}_grader"


def main() -> None:
    tasks = find_legacy_tasks()
    print(f"Found {len(tasks)} legacy tasks")

    # Build canonical shared packages first.
    shared_built: dict[str, Path] = {}
    for group, info in SHARED_GROUPS.items():
        group_tasks = [t for t in tasks if t.parent == EXAMPLES / group]
        if not group_tasks:
            continue
        sources = {(t / "eval" / "grader.py").read_bytes() for t in group_tasks}
        assert len(sources) == 1, f"{group} grader.py files differ; refusing to share"
        canonical = EXAMPLES / group / "_grader"
        write_package(
            canonical,
            info["pkg"],
            info["description"],
            (group_tasks[0] / "eval" / "grader.py").read_text(),
        )
        shared_built[group] = canonical
        print(f"Wrote shared package {canonical}")

    for task_dir in tasks:
        group = task_dir.parent.name if task_dir.parent.parent == EXAMPLES else None
        if group in SHARED_GROUPS and task_dir.parent == EXAMPLES / group:
            info = SHARED_GROUPS[group]
            pkg, extra_setup = info["pkg"], info["extra_setup"]
            grader_dir = task_dir / "grader"
            if grader_dir.exists():
                shutil.rmtree(grader_dir)
            shutil.copytree(shared_built[group], grader_dir)
        else:
            pkg, extra_setup = slug_for(task_dir), []
            rel = str(task_dir.relative_to(EXAMPLES))
            description = f"CORAL grader for the {rel} task."
            write_package(
                task_dir / "grader",
                pkg,
                description,
                (task_dir / "eval" / "grader.py").read_text(),
                extra_deps=TASK_DEPS.get(rel),
            )
        patch_task_yaml(task_dir / "task.yaml", pkg, extra_setup)
        remove_legacy_grader(task_dir)

    print(f"Migrated {len(tasks)} tasks")


if __name__ == "__main__":
    main()
