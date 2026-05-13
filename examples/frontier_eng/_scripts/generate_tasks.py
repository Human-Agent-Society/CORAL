#!/usr/bin/env python3
"""Generate CORAL example directories from a Frontier-Engineering checkout.

For each leaf benchmark (a directory whose ``frontier_eval/`` contains an
``eval_command.txt``), this script writes::

    examples/frontier_eng/<Domain>/<Task>/
    ├── seed/
    │   ├── (the benchmark's own files)
    │   └── _parent/   # parent-domain shared files (frontier_eval/, data/, ...)
    ├── grader/        # copy of examples/frontier_eng/_grader/ (self-contained)
    └── task.yaml      # CORAL config wired to ./grader

The generator rewrites placeholders in ``frontier_eval/eval_command.txt``:
``{repo_root}/benchmarks/<Domain>/<file>`` becomes
``{benchmark}/_parent/<file>`` so the seed is self-contained — the CORAL
grader resolves ``{benchmark}`` to the seed root and the parent files live
underneath.

Usage::

    python examples/frontier_eng/_scripts/generate_tasks.py \\
        --source /tmp/frontier_eng_clone \\
        --dest examples/frontier_eng \\
        [--only InventoryOptimization/general_meio]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import textwrap
from pathlib import Path

LEAF_MARKER = "frontier_eval/eval_command.txt"
PARENT_DIRNAME = "_parent"
RUNTIME_DIRNAME = "_runtime"
GRADER_SOURCE_DIRNAME = "_grader"
GRADER_DEST_DIRNAME = "grader"
DEFAULT_TIMEOUT_S = 600
DEFAULT_MODEL = "claude-opus-4-6"

REQUIREMENTS_FILES = (
    "requirements.txt",
    "requirements-task.txt",
    "verification/requirements.txt",
)

ENV_SPECS_RELDIR = "scripts/env/specs"
DEFAULT_ENV = "frontier-eval-driver"

ENV_OVERRIDES: dict[str, str] = {
    "SingleCellAnalysis/predict_modality": "frontier-v1-main",
    "QuantumComputing/task_01_routing_qftentangled": "frontier-v1-main",
    "QuantumComputing/task_02_clifford_t_synthesis": "frontier-v1-main",
    "QuantumComputing/task_03_cross_target_qaoa": "frontier-v1-main",
    "SustainableDataCenterControl/hand_written_control": "frontier-v1-sustaindc",
    "ReactionOptimisation/snar_multiobjective": "frontier-v1-summit",
    "ReactionOptimisation/mit_case1_mixed": "frontier-v1-summit",
    "ReactionOptimisation/reizman_suzuki_pareto": "frontier-v1-summit",
    "ReactionOptimisation/dtlz2_pareto": "frontier-v1-summit",
    "Optics/adaptive_constrained_dm_control": "frontier-v1-main",
    "Optics/adaptive_temporal_smooth_control": "frontier-v1-main",
    "Optics/adaptive_energy_aware_control": "frontier-v1-main",
    "Optics/adaptive_fault_tolerant_fusion": "frontier-v1-main",
    "Optics/phase_fourier_pattern_holography": "frontier-v1-main",
    "Optics/phase_dammann_uniform_orders": "frontier-v1-main",
    "Optics/phase_weighted_multispot_single_plane": "frontier-v1-main",
    "Optics/phase_large_scale_weighted_spot_array": "frontier-v1-main",
    "Optics/fiber_wdm_channel_power_allocation": "frontier-v1-main",
    "Optics/fiber_mcs_power_scheduling": "frontier-v1-main",
    "Optics/fiber_dsp_mode_scheduling": "frontier-v1-main",
    "Optics/fiber_guardband_spectrum_packing": "frontier-v1-main",
    "Optics/holographic_multifocus_power_ratio": "frontier-v1-main",
    "Optics/holographic_multiplane_focusing": "frontier-v1-main",
    "Optics/holographic_multispectral_focusing": "frontier-v1-main",
    "Optics/holographic_polarization_multiplexing": "frontier-v1-main",
    "InventoryOptimization/tree_gsm_safety_stock": "frontier-v1-main",
    "InventoryOptimization/general_meio": "frontier-v1-main",
    "InventoryOptimization/joint_replenishment": "frontier-v1-main",
    "InventoryOptimization/finite_horizon_dp": "frontier-v1-main",
    "InventoryOptimization/disruption_eoqd": "frontier-v1-main",
    "PyPortfolioOpt/robust_mvo_rebalance": "frontier-v1-main",
    "PyPortfolioOpt/discrete_rebalance_mip": "frontier-v1-main",
    "PyPortfolioOpt/cvar_stress_control": "frontier-v1-main",
    "JobShop/abz": "frontier-v1-main",
    "JobShop/ft": "frontier-v1-main",
    "JobShop/la": "frontier-v1-main",
    "JobShop/orb": "frontier-v1-main",
    "JobShop/swv": "frontier-v1-main",
    "JobShop/ta": "frontier-v1-main",
    "JobShop/yn": "frontier-v1-main",
    "Robotics/DynamicObstacleAvoidanceNavigation": "frontier-v1-main",
    "Robotics/PIDTuning": "frontier-v1-main",
    "Robotics/UAVInspectionCoverageWithWind": "frontier-v1-main",
    "Robotics/QuadrupedGaitOptimization": "frontier-v1-main",
    "Robotics/RobotArmCycleTimeOptimization": "frontier-v1-main",
    "Robotics/CoFlyersVasarhelyiTuning": "frontier-v1-main",
    "Aerodynamics/CarAerodynamicsSensing": "frontier-v1-kernel",
    "KernelEngineering/MLA": "frontier-v1-kernel",
    "KernelEngineering/TriMul": "frontier-v1-kernel",
    "KernelEngineering/FlashAttention": "frontier-v1-kernel",
    "MolecularMechanics/diverse_conformer_portfolio": "frontier-v1-main",
    "MolecularMechanics/torsion_profile_fitting": "frontier-v1-main",
    "MolecularMechanics/weighted_parameter_coverage": "frontier-v1-main",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Root of the Frontier-Engineering checkout (the dir that contains benchmarks/).",
    )
    parser.add_argument(
        "--dest",
        required=True,
        type=Path,
        help="Output directory (typically examples/frontier_eng).",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only generate the given benchmark id(s). Repeatable.",
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove an existing target directory before writing."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be generated without writing."
    )
    args = parser.parse_args()

    benchmarks_root = args.source / "benchmarks"
    if not benchmarks_root.is_dir():
        print(f"error: benchmarks/ not found under {args.source}", file=sys.stderr)
        return 2

    env_specs = _load_env_specs(args.source)

    leaves = sorted(_discover_leaf_tasks(benchmarks_root))
    if args.only:
        only = set(args.only)
        leaves = [b for b in leaves if b in only]
        if not leaves:
            print(
                f"error: --only filter matched no tasks. Known: {sorted(_discover_leaf_tasks(benchmarks_root))}",
                file=sys.stderr,
            )
            return 2

    print(f"discovered {len(leaves)} leaf task(s)")
    for benchmark_id in leaves:
        target = args.dest / benchmark_id
        if args.dry_run:
            env = ENV_OVERRIDES.get(benchmark_id, DEFAULT_ENV)
            print(f"  [dry-run] would generate {benchmark_id} (env={env}) -> {target}")
            continue
        try:
            _generate_one(
                source_root=args.source,
                benchmarks_root=benchmarks_root,
                benchmark_id=benchmark_id,
                target_dir=target,
                clean=args.clean,
                env_specs=env_specs,
            )
            print(f"  ✓ {benchmark_id}")
        except Exception as e:
            print(f"  ✗ {benchmark_id}: {type(e).__name__}: {e}", file=sys.stderr)

    return 0


def _load_env_specs(source_root: Path) -> dict[str, dict]:
    """Load each scripts/env/specs/<env>.json file as a dict, keyed by env name."""
    specs_dir = source_root / ENV_SPECS_RELDIR
    out: dict[str, dict] = {}
    if not specs_dir.is_dir():
        return out
    for json_path in sorted(specs_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            out[data["name"]] = data
    return out


def _discover_leaf_tasks(benchmarks_root: Path) -> list[str]:
    out: list[str] = []
    for marker in benchmarks_root.glob(f"**/{LEAF_MARKER}"):
        task_dir = marker.parent.parent
        rel = task_dir.relative_to(benchmarks_root).as_posix()
        out.append(rel)
    return out


def _generate_one(
    *,
    source_root: Path,
    benchmarks_root: Path,
    benchmark_id: str,
    target_dir: Path,
    clean: bool,
    env_specs: dict[str, dict],
) -> None:
    src_task_dir = (benchmarks_root / benchmark_id).resolve()
    seed_dir = target_dir / "seed"

    if target_dir.exists():
        if clean:
            shutil.rmtree(target_dir)
        else:
            shutil.rmtree(seed_dir, ignore_errors=True)

    seed_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        src_task_dir,
        seed_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"),
    )

    parent_files_copied = _maybe_copy_parent_shared(
        benchmarks_root=benchmarks_root,
        benchmark_id=benchmark_id,
        seed_dir=seed_dir,
    )

    if parent_files_copied:
        _rewrite_eval_command(seed_dir, benchmark_id)

    env_name = ENV_OVERRIDES.get(benchmark_id, DEFAULT_ENV)
    runtime_setup = _bundle_runtime_requirements(
        source_root=source_root,
        seed_dir=seed_dir,
        env_name=env_name,
        env_specs=env_specs,
    )

    extra_setup = _detect_workspace_setup(seed_dir, has_runtime_pyproject=bool(runtime_setup)) + runtime_setup

    description = _read_description(seed_dir, benchmark_id)
    tips = _read_tips(seed_dir, env_name=env_name)
    timeout = _detect_timeout(benchmark_id)

    _copy_grader_into_task(target_dir=target_dir)

    yaml_text = _render_task_yaml(
        benchmark_id=benchmark_id,
        target_dir=target_dir,
        description=description,
        tips=tips,
        timeout=timeout,
        extra_setup=extra_setup,
    )
    (target_dir / "task.yaml").write_text(yaml_text, encoding="utf-8")


def _maybe_copy_parent_shared(
    *,
    benchmarks_root: Path,
    benchmark_id: str,
    seed_dir: Path,
) -> bool:
    parts = benchmark_id.split("/")
    if len(parts) < 2:
        return False
    parent_rel = "/".join(parts[:-1])
    parent_dir = (benchmarks_root / parent_rel).resolve()
    if not parent_dir.is_dir():
        return False

    parent_eval = parent_dir / "frontier_eval"
    has_shared = parent_eval.is_dir() and not (parent_eval / "eval_command.txt").is_file()
    if not has_shared:
        return False

    parent_target = seed_dir / PARENT_DIRNAME
    parent_target.mkdir(exist_ok=True)

    sibling_tasks = {
        child.name
        for child in parent_dir.iterdir()
        if child.is_dir() and (child / LEAF_MARKER).is_file()
    }

    copied_anything = False
    for child in parent_dir.iterdir():
        if child.name in sibling_tasks:
            continue
        if child.name in {".git", "__pycache__", ".DS_Store"}:
            continue
        dst = parent_target / child.name
        if child.is_dir():
            shutil.copytree(
                child,
                dst,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"),
            )
        else:
            shutil.copy2(child, dst)
        copied_anything = True

    return copied_anything


def _rewrite_eval_command(seed_dir: Path, benchmark_id: str) -> None:
    parts = benchmark_id.split("/")
    if len(parts) < 2:
        return
    parent_rel = "/".join(parts[:-1])
    cmd_path = seed_dir / "frontier_eval" / "eval_command.txt"
    if not cmd_path.is_file():
        return
    text = cmd_path.read_text(encoding="utf-8")

    pattern = re.compile(r"\{repo_root(?:_raw)?\}/benchmarks/" + re.escape(parent_rel) + r"/")
    new_text = pattern.sub("{benchmark}/" + PARENT_DIRNAME + "/", text)
    if new_text != text:
        cmd_path.write_text(new_text, encoding="utf-8")


def _detect_workspace_setup(seed_dir: Path, *, has_runtime_pyproject: bool = False) -> list[str]:
    # When a runtime spec produced pyproject.toml + `uv sync`, the verification
    # requirements are redundant (and often pin old torch versions that have no
    # wheels for the Python uv picks for the worktree venv). `uv sync` against
    # the generated pyproject is the source of truth.
    if has_runtime_pyproject:
        return []
    setup: list[str] = []
    seen: set[str] = set()
    for rel in REQUIREMENTS_FILES:
        candidate = seed_dir / rel
        if candidate.is_file():
            cmd = f"uv pip install -r {rel}"
            if cmd not in seen:
                setup.append(cmd)
                seen.add(cmd)

    parent_dir = seed_dir / PARENT_DIRNAME
    if parent_dir.is_dir():
        for rel in REQUIREMENTS_FILES:
            candidate = parent_dir / rel
            if candidate.is_file():
                cmd = f"uv pip install -r {PARENT_DIRNAME}/{rel}"
                if cmd not in seen:
                    setup.append(cmd)
                    seen.add(cmd)
    return setup


def _bundle_runtime_requirements(
    *,
    source_root: Path,
    seed_dir: Path,
    env_name: str,
    env_specs: dict[str, dict],
) -> list[str]:
    """Bundle the runtime env's requirement files + packages into seed/_runtime/.

    Mirrors what scripts/env/setup_v1_task_envs.sh does for the host envs, but
    folded down into per-task ``workspace.setup`` commands so each CORAL
    worktree gets its own venv with the right deps.

    Also writes a top-level ``pyproject.toml`` that pins the same deps so
    ``uv run --project <codebase>`` works inside the daemon's detached
    worktree (where ``.venv`` doesn't exist yet) — the grader uses
    ``self.get_python_command()`` to find the python binary with task deps.
    """
    spec = env_specs.get(env_name)
    if spec is None:
        return []

    runtime_dir = seed_dir / RUNTIME_DIRNAME
    runtime_dir.mkdir(exist_ok=True)

    aggregated_lines: list[str] = []
    parsed_deps: list[str] = []
    for rel in spec.get("requirements") or []:
        src = (source_root / rel).resolve()
        if not src.is_file():
            aggregated_lines.append(f"# WARNING: missing requirements file in source repo: {rel}")
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        aggregated_lines.append(f"# from {rel}")
        aggregated_lines.append(text.rstrip())
        aggregated_lines.append("")
        parsed_deps.extend(_parse_requirements(text))

    setup_cmds: list[str] = []
    if aggregated_lines:
        req_path = runtime_dir / "requirements.txt"
        req_path.write_text("\n".join(aggregated_lines) + "\n", encoding="utf-8")

    packages = [str(p).strip() for p in (spec.get("packages") or []) if str(p).strip()]
    parsed_deps.extend(packages)

    notes = spec.get("notes") or []
    if notes or spec.get("system_requirements") or aggregated_lines:
        readme = runtime_dir / "README.md"
        lines = [
            f"# Runtime: {env_name}",
            "",
            "Bundled from `scripts/env/specs/" + env_name + ".json` in the upstream",
            "[Frontier-Engineering](https://github.com/EinsiaLab/Frontier-Engineering) repo.",
            "",
        ]
        if spec.get("python"):
            lines.append(f"- Python: {spec['python']}")
        sys_reqs = spec.get("system_requirements") or []
        if sys_reqs:
            lines.append(f"- System packages required (install separately): {', '.join(sys_reqs)}")
        if notes:
            lines.append("")
            lines.append("## Notes from upstream")
            for note in notes:
                lines.append(f"- {note}")
        readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if parsed_deps:
        _write_seed_pyproject(seed_dir, parsed_deps, python_version=spec.get("python") or "3.11")
        setup_cmds.append("uv sync")
    return setup_cmds


def _parse_requirements(text: str) -> list[str]:
    """Convert a requirements.txt to a list of pyproject deps.

    Drops comments, blank lines, BOM characters, and ``-r``/``-c`` includes.
    Preserves version specifiers, environment markers, and extras as-is.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r", "-c", "--")):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def _write_seed_pyproject(seed_dir: Path, deps: list[str], *, python_version: str) -> None:
    """Emit a minimal pyproject.toml for the seed pinning runtime deps.

    The grader's ``self.get_python_command()`` detects this and runs the
    benchmark eval via ``uv run --project <codebase>`` so deps are visible
    even inside the daemon's detached worktree.

    A bare upstream version like ``"3.12"`` is emitted as ``>=3.12,<3.13``
    rather than ``>=3.12`` — uv would otherwise pick the newest matching
    Python (3.13+) and fail to install deps that only ship cp312 wheels
    (e.g. ``ortools==9.10.4067``). Anything that already starts with an
    operator (``>=``, ``==``, ``~=``) is passed through verbatim.
    """
    pyproject_path = seed_dir / "pyproject.toml"
    if pyproject_path.exists():
        return
    py_min = python_version.strip() or "3.11"
    if py_min.startswith((">", "=", "<", "~", "!")):
        py_spec = py_min
    else:
        py_spec = _pin_to_minor(py_min)
    deps_block = ",\n    ".join(_toml_quote(d) for d in deps)
    text = (
        "# Generated by examples/frontier_eng/_scripts/generate_tasks.py\n"
        "# Pins the runtime deps the benchmark eval needs. Edit freely if you\n"
        "# need to add a package — the grader will pick it up via `uv run`.\n"
        "[project]\n"
        'name = "frontier-eng-task-runtime"\n'
        'version = "0.0.0"\n'
        f'requires-python = "{py_spec}"\n'
        "dependencies = [\n"
        f"    {deps_block},\n"
        "]\n"
    )
    pyproject_path.write_text(text, encoding="utf-8")


def _pin_to_minor(version: str) -> str:
    # "3.12" -> ">=3.12,<3.13"; falls back to ">=<version>" for malformed input.
    parts = version.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        major, minor = int(parts[0]), int(parts[1])
        return f">={major}.{minor},<{major}.{minor + 1}"
    return f">={version}"


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _shell_quote(value: str) -> str:
    if not value:
        return "''"
    safe = all(c.isalnum() or c in "._/-=+,@:" for c in value)
    if safe:
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _read_description(seed_dir: Path, benchmark_id: str) -> str:
    for filename in ("Task.md", "README.md"):
        path = seed_dir / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            return _trim_long(text, max_chars=8000)
    return f"Frontier-Engineering benchmark `{benchmark_id}`. See seed files for details."


def _read_tips(seed_dir: Path, *, env_name: str) -> str | None:
    constraints = seed_dir / "frontier_eval" / "constraints.txt"
    parts: list[str] = []
    if constraints.is_file():
        parts.append(constraints.read_text(encoding="utf-8", errors="replace").rstrip())
    parts.append(
        textwrap.dedent(f"""\
        Workflow notes (CORAL):
        - The seed mirrors the benchmark directory from EinsiaLab/Frontier-Engineering.
        - Runtime: deps are pulled from `_runtime/requirements.txt` (env: `{env_name}`).
          Edit it if you need additional packages installed in the worktree venv.
        - The grader reads `frontier_eval/` metadata to run the benchmark's eval command.
        - Edit the candidate file referenced by `frontier_eval/candidate_destination.txt`
          (default falls back to `frontier_eval/initial_program.txt`).
        - The eval is staged in a sandbox copy of the codebase; outputs land at
          `<sandbox>/metrics.json` (combined_score + valid).
        - If the seed contains a `_parent/` directory, those are shared files copied
          from the parent benchmark domain — read-only by convention.""").rstrip()
    )
    if not parts:
        return None
    return "\n\n".join(parts)


def _detect_timeout(benchmark_id: str) -> int:
    overrides = {
        "EngDesign": 7200,
        "KernelEngineering/MLA": 1800,
        "KernelEngineering/TriMul": 1800,
        "KernelEngineering/FlashAttention": 1800,
        "Aerodynamics/CarAerodynamicsSensing": 1800,
        "Astrodynamics/MannedLunarLanding": 1800,
        "ParticlePhysics/MuonTomography": 1800,
        "ParticlePhysics/ProtonTherapyPlanning": 1800,
        "SustainableDataCenterControl/hand_written_control": 1800,
        "MolecularMechanics/diverse_conformer_portfolio": 1800,
        "MolecularMechanics/torsion_profile_fitting": 1800,
        "MolecularMechanics/weighted_parameter_coverage": 1800,
        "SingleCellAnalysis/perturbation_prediction": 1800,
        "SingleCellAnalysis/predict_modality": 1800,
        "SingleCellAnalysis/denoising": 1800,
        "SingleCellAnalysis/denoising_ttt": 1800,
        "JobShop/abz": 1200,
        "JobShop/ft": 1200,
        "JobShop/la": 1200,
        "JobShop/orb": 1200,
        "JobShop/swv": 1200,
        "JobShop/ta": 1200,
        "JobShop/yn": 1200,
        "Robotics/QuadrupedGaitOptimization": 1200,
        "Robotics/UAVInspectionCoverageWithWind": 1200,
        "Robotics/CoFlyersVasarhelyiTuning": 1200,
        "StructuralOptimization/ISCSO2015": 1200,
        "StructuralOptimization/ISCSO2023": 1200,
        "StructuralOptimization/PyMOTOSIMPCompliance": 1200,
        "StructuralOptimization/TopologyOptimization": 1200,
    }
    return overrides.get(benchmark_id, DEFAULT_TIMEOUT_S)


def _copy_grader_into_task(*, target_dir: Path) -> None:
    """Copy the canonical ``_grader/`` package into the task dir as ``grader/``.

    The shared ``_grader/`` directory at ``examples/frontier_eng/_grader/`` is
    the source of truth. We copy it into each task dir so each task is fully
    self-contained — ``task.yaml`` then says ``uv pip install -e ./grader``,
    matching the convention used by ``examples/swebench-verified/`` and
    ``examples/erdos/``. Self-containment matters for:
      - ``run.session=docker`` (only the task dir is mounted at ``/task``)
      - copying a single task dir somewhere else for distribution / debug

    The source is found by walking up from ``target_dir`` to the
    ``frontier_eng/`` root that contains ``_grader/``.
    """
    grader_src = _find_grader_source(target_dir)
    if grader_src is None:
        raise RuntimeError(
            f"could not locate {GRADER_SOURCE_DIRNAME}/ above {target_dir} "
            f"(walked up looking for a 'frontier_eng' parent)."
        )
    grader_dst = target_dir / GRADER_DEST_DIRNAME
    if grader_dst.exists():
        shutil.rmtree(grader_dst)
    shutil.copytree(
        grader_src,
        grader_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "*.egg-info"),
    )


def _find_grader_source(target_dir: Path) -> Path | None:
    parts = target_dir.resolve().parts
    try:
        idx = parts.index("frontier_eng")
    except ValueError:
        return None
    candidate = Path(*parts[: idx + 1]) / GRADER_SOURCE_DIRNAME
    return candidate if candidate.is_dir() else None


def _trim_long(text: str, *, max_chars: int) -> str:
    text = text.rstrip()
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars].rstrip()
        + "\n\n[... truncated, see seed README.md / Task.md for the full text ...]"
    )


def _render_task_yaml(
    *,
    benchmark_id: str,
    target_dir: Path,
    description: str,
    tips: str | None,
    timeout: int,
    extra_setup: list[str],
) -> str:
    indent = "    "
    description_block = textwrap.indent(description.rstrip(), indent)
    yaml_lines = [
        "# Generated by examples/frontier_eng/_scripts/generate_tasks.py",
        "# Source: https://github.com/EinsiaLab/Frontier-Engineering",
        f"# Benchmark id: {benchmark_id}",
        "",
        "task:",
        f'  name: "Frontier-Eng · {benchmark_id}"',
        "  description: |",
        description_block,
    ]

    if tips:
        tips_block = textwrap.indent(tips.rstrip(), indent)
        yaml_lines.append("  tips: |")
        yaml_lines.append(tips_block)

    workspace_repo_path = (target_dir / "seed").as_posix()

    yaml_lines.extend(
        [
            "",
            "grader:",
            '  entrypoint: "frontier_eng_grader.grader:Grader"',
            "  setup:",
            f'    - "uv pip install -e ./{GRADER_DEST_DIRNAME}"',
            f"  timeout: {timeout}",
            "  direction: maximize",
            "  args:",
            f'    benchmark_id: "{benchmark_id}"',
            "",
            "agents:",
            "  count: 1",
            "  runtime: claude_code",
            f"  model: {DEFAULT_MODEL}",
            "",
            "workspace:",
            '  results_dir: "./results"',
            f'  repo_path: "./{workspace_repo_path}"',
        ]
    )

    if extra_setup:
        yaml_lines.append("  setup:")
        for cmd in extra_setup:
            yaml_lines.append(f'    - "{cmd}"')

    yaml_lines.extend(
        [
            "",
            "run:",
            "  verbose: false",
            "  ui: false",
            "  session: tmux",
            "",
        ]
    )

    return "\n".join(yaml_lines)


if __name__ == "__main__":
    raise SystemExit(main())
