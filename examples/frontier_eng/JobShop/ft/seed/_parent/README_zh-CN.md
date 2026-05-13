# JobShop 基准工作区

这个目录把 7 个经典 JSSP 基准家族统一成同一套训练/评测结构。

## 共同点

- 全部是**经典 JSSP**：每个工件的工序顺序固定，每道工序只在一台机器上加工。
- 目标都是最小化 **makespan（总完工时间）**。
- 每个实例都带有元数据：`optimum`（若已知）、`lower_bound`、`upper_bound`、`reference`。
- 每个家族目录结构一致：
  - `README.md`, `README_zh-CN.md`
  - `Task.md`, `Task_zh-CN.md`
  - `baseline/init.py`（简单贪心基线，纯 Python 标准库实现）
  - `verification/reference.py`（可调用 OR-Tools CP-SAT 的参考实现）
  - `verification/evaluate.py`（同时评测 baseline 和 reference 并打分）

## 主要差异

| 家族 | 实例数 | 典型规模（工件 x 机器） | 难度趋势 |
|---|---:|---|---|
| FT | 3 | 6x6, 10x10, 20x5 | 入门教学友好 |
| LA | 40 | 10x5 到 30x10 | 中等规模，最常用 |
| ABZ | 5 | 10x10, 20x15 | 中到高难 |
| ORB | 10 | 10x10 | 中等，便于横向比较 |
| SWV | 20 | 20x10, 20x15, 50x10 | 规模更大、难度更高 |
| YN | 4 | 20x20 | 高难、约束密集 |
| TA | 80 | 15x15 到 100x20 | 大规模压力测试 |

## 本目录评分规则

- **最佳已知得分**：`score_best = min(100, 100 * target / makespan)`
  - 若 `optimum` 已知，`target = optimum`；否则 `target = upper_bound`
- **理论上限对比得分**：`score_lb = min(100, 100 * lower_bound / makespan)`
  - 在该公式下，理论上限是 `100`。
- 分数越高越好。

## 环境依赖

- Python：`>=3.10`
- 在仓库根目录安装统一依赖配置：
  - `pip install -r JobShop/requirements.txt`
- baseline（`baseline/init.py`）：仅依赖 Python 标准库。
- reference + evaluate 使用 `job_shop_lib` 的 Python 包与 OR-Tools（`ortools`）。
- 基准实例数据文件已随仓库提供：`JobShop/data/benchmark_instances.json`。
  该文件来源于 `job_shop_lib` 项目：
  https://github.com/Pabloo22/job_shop_lib.git

## `evaluate.py` 参数说明

- `--instances`：可选，显式指定实例名列表。
  不传时评测所选家族全部实例。
- `--max-instances`：可选，限制评测实例数量。
  在可选 `--instances` 过滤后，取前 N 个。
- `--reference-time-limit`：参考求解器每个实例的时间上限（秒）。
  默认值：`10.0`。

## 运行示例

```bash
python JobShop/ft/verification/evaluate.py --max-instances 3 --reference-time-limit 5
python JobShop/ta/verification/evaluate.py --max-instances 2 --reference-time-limit 5
```

## 已接入 Frontier Eval Unified

已完成 7 个子任务的 unified 接入，可直接使用：

- `task=unified task.benchmark=JobShop/abz`
- `task=unified task.benchmark=JobShop/ft`
- `task=unified task.benchmark=JobShop/la`
- `task=unified task.benchmark=JobShop/orb`
- `task=unified task.benchmark=JobShop/swv`
- `task=unified task.benchmark=JobShop/ta`
- `task=unified task.benchmark=JobShop/yn`

每个家族目录下的 `frontier_eval/` 元数据会调用统一评测脚本：
`benchmarks/JobShop/frontier_eval/evaluate_unified.py`。

## Unified 运行方式（双环境）

推荐配置：

- `frontier_eval` driver 进程：`frontier-eval-driver`
- JobShop evaluator Python：`uv-env:frontier-v1-main`（或者显式传绝对解释器路径）

单个家族运行示例（以 `abz` 为例）：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=JobShop/abz \
  task.runtime.python_path=uv-env:frontier-v1-main \
  algorithm.iterations=0
```

快速自检（7 个家族都跑 1 个实例，reference 每个实例 1 秒）：

```bash
for fam in abz ft la orb swv ta yn; do
  .venvs/frontier-eval-driver/bin/python -m frontier_eval \
    task=unified \
    task.benchmark=JobShop/${fam} \
    task.runtime.python_path=uv-env:frontier-v1-main \
    +task.runtime.env.JOBSHOP_EVAL_MAX_INSTANCES=1 \
    +task.runtime.env.JOBSHOP_REFERENCE_TIME_LIMIT=1 \
    algorithm.iterations=0
done
```

可用运行参数（通过 unified runtime env 传入）：

- `+task.runtime.env.JOBSHOP_EVAL_MAX_INSTANCES=<N>`：最多评测前 N 个实例。
- `+task.runtime.env.JOBSHOP_REFERENCE_TIME_LIMIT=<seconds>`：reference 每实例时间上限。
- `+task.runtime.env.JOBSHOP_EVAL_INSTANCES='ta01 ta02'`：仅评测指定实例。

## 运行时间说明（默认配置）

默认不限制实例数，且 `reference-time-limit=10s`。粗略上界可按
`实例数 x 10s + 建模/IO 开销` 估算：

| 家族 | 默认实例数 | 粗略时间上界 | 说明 |
|---|---:|---:|---|
| FT | 3 | ~30s+ | 短 |
| ABZ | 5 | ~50s+ | 短 |
| ORB | 10 | ~100s+ | 中等 |
| YN | 4 | ~40s+ | 中等（实例更稠密） |
| SWV | 20 | ~200s+ | 较长 |
| LA | 40 | ~400s+ | 长 |
| TA | 80 | ~800s+ | 很长（压力测试） |

其中 `LA/SWV/TA` 更容易出现长耗时，特别是 `TA`。
建议开发调试阶段先设置 `JOBSHOP_EVAL_MAX_INSTANCES` 与较小的
`JOBSHOP_REFERENCE_TIME_LIMIT`。

## 为什么这个 benchmark 仍然很难

- baseline 分数在 `80` 左右并不代表“接近最优”。当 `target = optimum` 时，
  `gap% = 100 * (100 / score - 1)`，所以 score=`80` 仍约有 `25%` 的差距。
- baseline 往往先拿到“容易的局部收益”，但后续提升需要在多工件、多机器上做
  全局组合优化，难度明显上升。
- 在高分区继续提分通常代价很高：从 80+ 提升到 90+，一般需要更强的搜索策略
  和更长计算时间。
- 当 `optimum` 未知时，`best-known score` 使用的是 `upper_bound`，因此分数高
  也不等于已经接近真实最优解。
