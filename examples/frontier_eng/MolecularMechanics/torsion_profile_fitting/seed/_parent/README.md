# OpenFF Optimization Tasks

## File Layout

```text
MolecularMechanics/
├── README.md
├── README_zh-CN.md
├── requirements.txt
├── Task.md
├── Task_zh-CN.md
├── frontier_eval/
│   └── run_eval.py
├── weighted_parameter_coverage/
│   ├── Task.md
│   ├── Task_zh-CN.md
│   ├── baseline/
│   │   └── init.py
│   ├── data/
│   │   └── raw_task.json
│   ├── frontier_eval/
│   │   ├── initial_program.txt
│   │   ├── eval_command.txt
│   │   └── ...
│   └── verification/
│       └── evaluate.py
├── diverse_conformer_portfolio/
│   ├── Task.md
│   ├── Task_zh-CN.md
│   ├── baseline/
│   │   └── init.py
│   ├── data/
│   │   └── raw_task.json
│   ├── frontier_eval/
│   │   ├── initial_program.txt
│   │   ├── eval_command.txt
│   │   └── ...
│   └── verification/
│       └── evaluate.py
└── torsion_profile_fitting/
    ├── Task.md
    ├── Task_zh-CN.md
    ├── baseline/
    │   └── init.py
    ├── data/
    │   └── raw_task.json
    ├── frontier_eval/
    │   ├── initial_program.txt
    │   ├── eval_command.txt
    │   └── ...
    └── verification/
        └── evaluate.py
```

## What Each Task Directory Contains

- `Task.md`
  - English task description
- `Task_zh-CN.md`
  - Chinese task description
- `baseline/init.py`
  - Starter solver
  - Intended to focus on optimization rather than chemistry libraries
- `data/raw_task.json`
  - Raw benchmark configuration
- `verification/evaluate.py`
  - `prepare` and `evaluate` entry points
- `frontier_eval/`
  - Unified-task metadata
  - Lets `python -m frontier_eval` evaluate the subtask directly

## Environment Setup

It is easiest to keep the framework environment and the benchmark runtime environment separate:

- `.venvs/frontier-eval-driver`
  - runs `python -m frontier_eval`
- `openff-dev`
  - a separately bootstrapped runtime that runs the actual MolecularMechanics evaluation

Recommended setup from the repository root:

```bash
bash init.sh
bash scripts/bootstrap/install_openff_dev.sh
source .venvs/frontier-eval-driver/bin/activate
```

If you already have both runtimes, run from the repository root:

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
.venvs/openff-dev/bin/python -m pip install -r benchmarks/MolecularMechanics/requirements.txt
./.venvs/openff-dev/bin/python scripts/bootstrap/verify_openff_dev.py --repo-root .
```

`openff-dev` is intentionally kept as a special runtime: the OpenFF stack is not fully reproducible with `uv` alone as of 2026.

The repository bootstrap installs that runtime into `.venvs/openff-dev` with `mamba`/`conda`, then runs a smoke verification:

```bash
bash scripts/bootstrap/install_openff_dev.sh
```

Notes:

- `benchmarks/MolecularMechanics/requirements.txt`
  - contains the Python-level dependencies
- `rdkit`, `openmm`, and `ambertools`
  - still come from the `mamba`/`conda-forge` side of the bootstrap
- For manual task execution
  - `.venvs/openff-dev` is enough
- For `frontier_eval`
  - the framework process stays in `frontier-eval-driver`
  - the benchmark evaluation process switches to `openff-dev`

## Frontier Eval (Unified)

All three subtasks are integrated through the unified task mechanism.

Shortcut task names:

| Subtask | Shortcut task name | Equivalent benchmark path | Measured runtime with `algorithm.iterations=0` |
|---|---|---|---|
| `weighted_parameter_coverage` | `molecular_mechanics_weighted_parameter_coverage` | `MolecularMechanics/weighted_parameter_coverage` | about `5.6s` |
| `diverse_conformer_portfolio` | `molecular_mechanics_diverse_conformer_portfolio` | `MolecularMechanics/diverse_conformer_portfolio` | about `5.5s` |
| `torsion_profile_fitting` | `molecular_mechanics_torsion_profile_fitting` | `MolecularMechanics/torsion_profile_fitting` | about `26.8s` |

These timings were measured on `2026-03-16` with:

- `.venvs/frontier-eval-driver/bin/python -m frontier_eval ...`
- `algorithm=openevolve`
- `algorithm.iterations=0`
- benchmark runtime environment `openff-dev`

Quick runs:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_weighted_parameter_coverage \
  algorithm=openevolve \
  algorithm.iterations=0

.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_diverse_conformer_portfolio \
  algorithm=openevolve \
  algorithm.iterations=0

.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_torsion_profile_fitting \
  algorithm=openevolve \
  algorithm.iterations=0
```

Equivalent explicit unified command:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=MolecularMechanics/torsion_profile_fitting \
  task.runtime.python_path=uv-env:openff-dev \
  algorithm=openevolve \
  algorithm.iterations=0
```

## Manual Workflow

Every task follows the same 3-step flow:

1. `prepare`
   - convert `data/raw_task.json` into algorithm-friendly input
2. run `baseline/init.py`
   - produce a candidate solution
3. `evaluate`
   - score that solution with the real benchmark rules

Example for `weighted_parameter_coverage`.

If you run from the task directory:

```bash
cd benchmarks/MolecularMechanics/weighted_parameter_coverage
mkdir -p outputs

python verification/evaluate.py prepare \
  --raw-task data/raw_task.json \
  --prepared-output outputs/prepared.json

python baseline/init.py \
  --prepared-input outputs/prepared.json \
  --solution-output outputs/solution.json

python verification/evaluate.py evaluate \
  --prepared-input outputs/prepared.json \
  --solution outputs/solution.json \
  --result-output outputs/result.json
```

If you run from the repository root:

```bash
mkdir -p benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs

python benchmarks/MolecularMechanics/weighted_parameter_coverage/verification/evaluate.py prepare \
  --raw-task benchmarks/MolecularMechanics/weighted_parameter_coverage/data/raw_task.json \
  --prepared-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json

python benchmarks/MolecularMechanics/weighted_parameter_coverage/baseline/init.py \
  --prepared-input benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json \
  --solution-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/solution.json

python benchmarks/MolecularMechanics/weighted_parameter_coverage/verification/evaluate.py evaluate \
  --prepared-input benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json \
  --solution benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/solution.json \
  --result-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/result.json
```

The other tasks follow the same pattern by replacing the task directory with:

- `diverse_conformer_portfolio`
- `torsion_profile_fitting`

## Runtime Notes

- `weighted_parameter_coverage`
  - one unified evaluation is about `5-6s`
- `diverse_conformer_portfolio`
  - one unified evaluation is about `5-6s`
- `torsion_profile_fitting`
  - one unified evaluation is about `25-30s`
  - most of the time is spent in `prepare`, where torsion scans and public profiles are built

If you run multi-iteration optimization, `torsion_profile_fitting` will accumulate noticeably more wall time than the other two tasks.

## Suggested Reading Order

1. Start with [Task.md](Task.md)
2. Open one task-specific `Task.md`
3. Inspect the corresponding `baseline/init.py`
