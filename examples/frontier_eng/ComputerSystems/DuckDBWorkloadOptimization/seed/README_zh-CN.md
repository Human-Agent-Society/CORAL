# DuckDB 负载优化任务

本任务的导航文档。

## 目标

在 DuckDB 中优化一组混合分析型 SQL 负载，包含两个耦合目标：

1. 选择可选物理结构（`CREATE INDEX`、可选物化视图表）。
2. 对部分查询进行 SQL 改写，同时保持语义严格等价。

该任务用于评估 agent 在真实 DuckDB benchmark 资产上的端到端性能优化能力。

## 官方来源一致性

本任务直接基于 DuckDB 上游 benchmark 文件，不使用捏造的 workload SQL：

- 来源仓库：`https://github.com/duckdb/duckdb`
- 来源提交：`ff4f70eeee83cfd3dae6577fc9b2b448d5fbdb35`
- 引入文件清单见 `references/problem_config.json`，并已复制到 `references/duckdb_official/`。

## 文件结构

- `Task.md`：任务契约与评分规则（英文）。
- `Task_zh-CN.md`：任务契约中文版本。
- `scripts/init.py`：最小可运行候选程序（`solve(problem) -> dict`）。
- `baseline/solution.py`：DuckDB 原生基线（不加额外索引/物化视图，使用官方原 SQL）。
- `verification/evaluator.py`：评测入口。
- `verification/requirements.txt`：评测最小依赖。
- `references/problem_config.json`：任务定义、约束上限、workload 映射。
- `references/duckdb_official/`：本任务使用的 DuckDB 官方 benchmark 文件副本。
- `frontier_eval/`：与统一评测框架对接的元数据。

## 环境准备

在仓库根目录执行：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/ComputerSystems/DuckDBWorkloadOptimization/verification/requirements.txt
```

## 快速运行

在仓库根目录运行：

```bash
python benchmarks/ComputerSystems/DuckDBWorkloadOptimization/verification/evaluator.py benchmarks/ComputerSystems/DuckDBWorkloadOptimization/scripts/init.py
```

或在任务目录运行：

```bash
cd benchmarks/ComputerSystems/DuckDBWorkloadOptimization
python verification/evaluator.py scripts/init.py
```

可运行的初始程序应输出 `valid=1.0`，且时间类指标为非零值。

## frontier_eval 任务名

Unified 模式：

```bash
python -m frontier_eval task=unified task.benchmark=ComputerSystems/DuckDBWorkloadOptimization algorithm.iterations=0
```

已注册短别名：

```bash
python -m frontier_eval task=duckdb_workload_optimization algorithm.iterations=0
```
