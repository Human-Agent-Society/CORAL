# Task 02: CVaR Stress-Controlled Allocation

This benchmark focuses on tail-risk-aware optimization under scenario returns.
The optimizer must satisfy return and exposure constraints while minimizing CVaR.

## Why this task matters

Production portfolios are often constrained by drawdown and stress mandates.
Variance alone is not enough for heavy-tailed markets, so scenario-based CVaR
optimization is widely used in risk committees.

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
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/cvar_stress_control/verification/evaluate.py
```

Run with `frontier_eval` unified task:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/cvar_stress_control \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

Runtime note: this evaluator repeatedly solves CVaR programs across seeds. A single `algorithm.iterations=0` run is typically around 9-18 seconds, and longer evolutionary runs should budget minutes.

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
