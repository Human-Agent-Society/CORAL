# Task 03: Discrete Rebalance with Lot Constraints (MIP)

This benchmark models execution-ready rebalancing: target portfolio weights must be converted
into integer lots under budget, turnover, and fee constraints.

## Why this task matters

Optimization outputs continuous weights, but trading systems place integer orders.
This gap creates a hard combinatorial optimization problem, especially with turnover limits
and transaction fees.

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
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/discrete_rebalance_mip/verification/evaluate.py
```

Run with `frontier_eval` unified task:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/discrete_rebalance_mip \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

Runtime note: this task solves mixed-integer programs (MIP), so runtime variance is higher. `algorithm.iterations=0` is commonly around 8-20 seconds, but can be longer on slower CPUs.

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
