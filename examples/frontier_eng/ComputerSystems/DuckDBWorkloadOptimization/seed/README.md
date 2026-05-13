# DuckDB Workload Optimization

Navigation document for this task.

## Goal

Optimize a mixed analytical SQL workload in DuckDB under two coupled objectives:

1. Select optional physical structures (`CREATE INDEX`, optional materialized-view tables).
2. Rewrite selected SQL queries while preserving exact query semantics.

This task is designed to evaluate whether an agent can improve end-to-end workload runtime on real DuckDB benchmark assets.

## Official Source Fidelity

This benchmark is grounded in upstream DuckDB benchmark files (no fabricated workload SQL):

- Source repository: `https://github.com/duckdb/duckdb`
- Source commit: `ff4f70eeee83cfd3dae6577fc9b2b448d5fbdb35`
- Imported files are listed in `references/problem_config.json` and copied under `references/duckdb_official/`.

## Files

- `Task.md`: task contract and scoring rules (English).
- `Task_zh-CN.md`: Chinese version of task contract.
- `scripts/init.py`: minimal runnable candidate program (`solve(problem) -> dict`).
- `baseline/solution.py`: DuckDB-native baseline (no extra index/MV; original official SQL).
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: minimal evaluator dependencies.
- `references/problem_config.json`: benchmark definition, limits, and workload mapping.
- `references/duckdb_official/`: copied official DuckDB benchmark files used by this task.
- `frontier_eval/`: unified task metadata for framework integration.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/ComputerSystems/DuckDBWorkloadOptimization/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/ComputerSystems/DuckDBWorkloadOptimization/verification/evaluator.py benchmarks/ComputerSystems/DuckDBWorkloadOptimization/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/ComputerSystems/DuckDBWorkloadOptimization
python verification/evaluator.py scripts/init.py
```

A valid starter is expected to produce `valid=1.0` and non-zero timing metrics.

## frontier_eval Task Name

Unified task mode:

```bash
python -m frontier_eval task=unified task.benchmark=ComputerSystems/DuckDBWorkloadOptimization algorithm.iterations=0
```

Registered short config alias:

```bash
python -m frontier_eval task=duckdb_workload_optimization algorithm.iterations=0
```
