# 任务说明：求解并评测 FT（Fisher & Thompson，1963） JSSP 实例

## 读者假设

默认你只有一般计算机背景，不要求你事先了解调度理论。

## 任务背景

一个 JSSP 实例包含：

- **工件（Job）**：每个工件由多道工序组成。
- **机器（Machine）**：每道工序必须在一台机器上加工。
- **加工时长**：每道工序有固定持续时间。
- **前后约束**：同一工件内，第 `k+1` 道工序必须在第 `k` 道结束后开始。
- **机器冲突约束**：同一时刻一台机器最多处理一道工序。

目标：最小化 **makespan**（最后一道工序完成的时间）。

## 本任务涉及的实例

- 前缀：`ft`
- 实例范围：ft06, ft10, ft20
- 规模范围：6x6, 10x10, 20x5
- 细分：完整列表：ft06(6x6)、ft10(10x10)、ft20(20x5)。

## 输入/输出定义

### 输入（概念层面）

每次运行读取一个基准实例，核心字段包括：

- `duration_matrix[j][k]`：工件 `j` 第 `k` 道工序的加工时间
- `machines_matrix[j][k]`：工件 `j` 第 `k` 道工序使用的机器
- 元数据：`optimum`、`lower_bound`、`upper_bound`、`reference`

### 输出（概念层面）

一个可行调度结果：

- 每道工序的开工时间
- 由此得到的机器时间线与工件完成时间
- 标量目标值：`makespan`

在本工作区中：

- baseline 输出纯 Python 字典（含 `makespan`）。
- reference 输出 `job_shop_lib` 的 `Schedule`。

## 预期结果

- 若 `optimum` 已知：理想是达到最优值。
- 若 `optimum` 未知：尽量接近最佳已知可行值（`upper_bound`）与理论极限（`lower_bound`）。
- baseline 目标是“稳定可行”，不是追求大规模实例上的最优性能。

## `verification/evaluate.py` 的评分方式

对每个实例、每个解的 makespan 记为 `C`：

1. 最佳已知得分：
   - `target = optimum`（若已知），否则 `upper_bound`
   - `score_best = min(100, 100 * target / C)`
2. 理论上限对比得分：
   - `score_lb = min(100, 100 * lower_bound / C)`

解释：

- 分数越高越好。
- `100` 表示达到目标值（或在 `score_lb` 下达到下界）。
- 脚本会输出逐实例得分和家族平均得分。

## 本目录实现说明

- `baseline/init.py`：
  - 使用简单的 `EST + SPT` 贪心派工。
  - 纯 Python 标准库实现，不依赖 `job_shop_lib`。
- `verification/reference.py`：
  - 使用允许调用外部库的 OR-Tools CP-SAT 参考实现。
- `verification/evaluate.py`：
  - 同时评测 baseline/reference。
  - 输出 makespan、耗时、最佳已知得分、下界得分。
  - 给出与理论上限得分（`score_lb` 上限 100）的对比。

## 运行方式

```bash
python JobShop/ft/verification/evaluate.py --max-instances 3 --reference-time-limit 5
python JobShop/ft/verification/evaluate.py --instances ft06 ft10 --reference-time-limit 10
```
