# Task 01: Robust Mean-Variance Rebalancing

This benchmark focuses on a realistic single-period portfolio rebalancing problem:
maximize risk-adjusted return under practical constraints (sector exposure, factor exposure,
weight bounds, and turnover limit), while paying transaction penalties.

## Why this task matters

A pure Markowitz optimizer is rarely deployable as-is. Real production systems must handle:
- exposure controls (sector constraints),
- style/risk controls (factor exposure constraints),
- implementation frictions (turnover and transaction costs),
- stable transitions from current holdings (`w_prev`) to new holdings (`w`).

This benchmark forces all of these constraints into one optimization problem.

## Environment Setup

Please install dependencies using the unified Task configuration:

```bash
pip install -r benchmarks/PyPortfolioOpt/requirements.txt
```

If you are running commands from this subfolder, use:

```bash
pip install -r ../requirements.txt
```

## Run

From repository root:

```bash
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/robust_mvo_rebalance/verification/evaluate.py
```

Run with `frontier_eval` unified task:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/robust_mvo_rebalance \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

Runtime note: this evaluator solves multiple convex programs per run and is slower than smoke tasks. A single `algorithm.iterations=0` run is typically around 8-15 seconds, and total time grows roughly linearly with iterations.

## Directory Structure

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── frontier_eval
│   ├── initial_program.txt
│   ├── candidate_destination.txt
│   ├── eval_command.txt
│   ├── agent_files.txt
│   ├── readonly_files.txt
│   ├── artifact_files.txt
│   └── constraints.txt
├── baseline
│   └── init.py
└── verification
    ├── reference.py
    └── evaluate.py
```
