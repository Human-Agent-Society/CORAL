# DiffSim Thermal Control

This task adapts the real additive-manufacturing build case from `differentiable-simulation-am` into a Frontier-Engineering benchmark.

## Upstream Source

The benchmark uses the original committed upstream geometry and toolpath files:

- `references/original/0.k`
- `references/original/toolpath.crs`

Source repository:

- `https://github.com/mojtabamozaffar/differentiable-simulation-am`

Important note:

- the upstream notebook references `data/target.npy` and `data/target_q.npy`,
- but those files are not published in the repository,
- so this benchmark keeps the original real case geometry/toolpath/material constants and defines a reproducible thermal-control objective on top of that real case.

## Benchmark Intent

The evolve target is still a gradient-based process optimizer, but now the cases are built from real layers extracted from the upstream toolpath instead of hand-authored synthetic profiles.

The current task optimizes normalized laser-power control knots for selected real build layers while balancing:

- tracking a target thermal trajectory,
- staying inside the solidus / liquidus process window,
- smooth control evolution,
- reasonable power usage.

## File Structure

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   ├── result_log.txt
│   └── solution.py
├── frontier_eval/
│   ├── agent_files.txt
│   ├── candidate_destination.txt
│   ├── constraints.txt
│   ├── copy_files.txt
│   ├── eval_command.txt
│   ├── eval_cwd.txt
│   ├── initial_program.txt
│   └── readonly_files.txt
├── references/
│   ├── cases.json
│   └── original/
│       ├── 0.k
│       └── toolpath.crs
├── scripts/
│   └── init.py
└── verification/
    ├── evaluator.py
    └── requirements.txt
```

## Evolve Target

- Evolve file: `scripts/init.py`
- Reference baseline: `baseline/solution.py`
- Allowed edit region: between `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END`

Required unchanged interfaces:

- `load_cases(case_file=None)`
- `simulate(params, case)`
- `baseline_solve(case, max_sim_calls=..., simulate_fn=...)`
- `solve(case, max_sim_calls=..., simulate_fn=...)`

## Real Cases

`references/cases.json` defines 4 benchmark cases derived from actual layers of the upstream toolpath:

- `toolpath_layer_01`
- `toolpath_layer_02`
- `toolpath_layer_27`
- `toolpath_layer_28`

Each case is built from:

- real path coordinates,
- real layer heights,
- real scan timing,
- original process constants used in the upstream notebook.

## How to Run

Install the documented validation dependencies first:

```bash
pip install -r verification/requirements.txt
```

From this task directory:

```bash
python verification/evaluator.py scripts/init.py
python verification/evaluator.py baseline/solution.py
```

With output files:

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
```

Unified mode from repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=AdditiveManufacturing/DiffSimThermalControl \
  task.runtime.conda_env=<your_env> \
  algorithm.iterations=0
```

If you follow the local setup used for validation here, replace `<your_env>` with `Engi`.

## Notes

- `verification/evaluator.py` contains its own canonical scoring path.
- `baseline/result_log.txt` stores one reference run output.
- This task now uses real upstream case files rather than the earlier surrogate-only case setup.

