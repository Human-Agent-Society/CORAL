# SustainDC `hand_written_control`

This subtask asks you to write a deterministic control policy for the three original SustainDC agents:

> **[ATTENTION] Must clone the vendored directory before running**:
> SustainDC relies on the `dc-rl` library. The `sustaindc/` directory is an empty placeholder. Run this before evaluation:
> `git clone https://github.com/HewlettPackard/dc-rl.git benchmarks/SustainableDataCenterControl/hand_written_control/sustaindc`

Or use the repository bootstrap helper:

```bash
python scripts/bootstrap/fetch_task_assets.py --target sustaindc
```

- `agent_ls`: load shifting
- `agent_dc`: cooling control
- `agent_bat`: battery dispatch

The evaluator runs four fixed scenarios and scores your policy against a noop controller in the same run.

## Layout

```text
benchmarks/SustainableDataCenterControl/hand_written_control/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── benchmark_core.py
├── baseline/
│   └── solution.py
├── frontier_eval/
│   ├── agent_files.txt
│   ├── constraints.txt
│   ├── copy_files.txt
│   ├── eval_command.txt
│   └── ...
├── patches/
│   └── sustaindc_optional_runtime.patch
├── sustaindc/                # vendored dc-rl checkout, based on upstream commit a92b475
└── verification/
    ├── evaluate.py
    └── last_eval.json
```

## Environment

From repository root:

```bash
bash init.sh
RUN_VALIDATION=0 bash scripts/env/setup_v1_task_envs.sh
```

For unified runs, also prepare the evaluation framework environment:

```bash
source .venvs/frontier-eval-driver/bin/activate
```

## What To Edit

Edit only:

`baseline/solution.py`

Keep `decide_actions(observations) -> dict` working. `reset_policy()` is optional.

## Direct Verification

Run from repository root:

```bash
.venvs/frontier-v1-sustaindc/bin/python benchmarks/SustainableDataCenterControl/hand_written_control/verification/evaluate.py
```

Or from this task directory:

```bash
cd benchmarks/SustainableDataCenterControl/hand_written_control
../../../.venvs/frontier-v1-sustaindc/bin/python verification/evaluate.py
```

Validated runtime on the provided setup: about `19.8s`.

The evaluator writes the latest structured report to `verification/last_eval.json`.

## frontier_eval (Unified)

This task is integrated through the unified task metadata under `frontier_eval/`.

Run from repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=SustainableDataCenterControl/hand_written_control \
  task.runtime.env_name=frontier-v1-sustaindc \
  algorithm=openevolve \
  algorithm.iterations=0
```

Validated runtime on the provided setup: about `25.8s`.

Runtime note: `algorithm.iterations=0` still executes one full benchmark evaluation of `baseline/solution.py`, but this task remained comfortably under the default `300s` unified timeout in the verified environment.

## Reproduce From A Fresh Upstream Clone

The patch in this directory is tested against upstream commit `a92b475`.

```bash
cd benchmarks/SustainableDataCenterControl/hand_written_control

git clone https://github.com/HewlettPackard/dc-rl.git sustaindc_fresh
git -C sustaindc_fresh checkout a92b475

.venvs/frontier-v1-sustaindc/bin/python -m pip install -r sustaindc_fresh/requirements.txt
git -C sustaindc_fresh apply patches/sustaindc_optional_runtime.patch

.venvs/frontier-v1-sustaindc/bin/python verification/evaluate.py --sustaindc-root sustaindc_fresh
```

## Why The Patch Exists

`patches/sustaindc_optional_runtime.patch` only changes upstream `sustaindc_env.py`.

It makes the benchmark-compatible runtime path explicit:

- `matplotlib` becomes optional, because this benchmark does not use render-time plotting
- dashboard imports become optional, because upstream `requirements.txt` does not install the dashboard stack
- render mode still fails with a clear error message if those optional dependencies are missing

## Notes

- The simulator is not perfectly bitwise deterministic, so small score drift between runs is normal.
- The benchmark always compares your policy against the noop reference inside the same evaluation run.
- For the full task definition, read `Task.md` or `Task_zh-CN.md`.
