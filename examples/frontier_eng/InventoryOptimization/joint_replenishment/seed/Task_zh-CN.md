# 任务 03 - 共享订货成本下的联合补货优化

## 背景
这是一个带共享固定成本的组合优化问题。

- 决策变量：基础补货周期 `T` 与每个 SKU 的补货倍数 `m_i`
- 约束：SKU `i` 仅能每 `m_i * T` 周期补货
- 目标：最小化长期订货成本 + 持有成本

## 工程场景
仓库需要协调 8 个 SKU 的补货。

- 每次联合补货会产生共享固定成本
- 每个 SKU 还有自己的订货成本和持有成本
- 你需要在“总成本更低”和“慢速 SKU 不要补货过慢”之间平衡

## 输入
输入都在任务代码中定义，由 `verification/evaluate.py` 统一执行。

- 共享固定成本、单品固定成本、持有成本、需求率：[`verification/evaluate.py`](verification/evaluate.py)
- baseline 策略：[`baseline/init.py`](baseline/init.py)
- stockpyl 参考策略：[`verification/reference.py`](verification/reference.py)

## 输出
运行评测后生成：

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## 评分方式（0 到 1）
`clip(x) = min(1, max(0, x))`

- `CostScore`（0.55）：相对独立 EOQ 基线的降本幅度
- `ResponsivenessScore`（0.30）：最长补货周期控制（目标 `<=1.8`，上限 `2.6`）
- `CoordinationScore`（0.15）：补货倍数种类越少，协同越好

总分：

`FinalScore = 0.55*CostScore + 0.30*ResponsivenessScore + 0.15*CoordinationScore`

## 算法对应关系
Baseline（`baseline/init.py`，不调用 stockpyl 优化器）：

- 实现方式：手工规则/启发式实现，不调用 stockpyl 优化求解器。
- 输入输出：通过 `solve(...)` 输出任务策略参数（如 CST、base-stock、(s,S)、Q 等），供 `verification/evaluate.py` 统一打分。

- 固定周期 + 需求分桶倍数规则
- 先按需求区间分配 `m_i`，再计算 `Q_i = d_i * m_i * T`

Reference（`verification/reference.py`，调用 stockpyl）：

- 实现方式：调用 stockpyl 对应模型的优化/动态规划/枚举/启发式 API 求解。
- 输入输出：同样通过 `solve(...)` 输出与 baseline 同结构的策略对象，确保评测过程可直接对比。

- `stockpyl.eoq.joint_replenishment_problem_silver_heuristic`
- Silver 启发式联合补货优化

Evaluator（`verification/evaluate.py`）：

- 直接调用 baseline 与 reference
- 对两种策略使用同一成本函数打分
- 输出详细指标与对比结果

## 运行方式
```bash
cd tasks/joint_replenishment
python verification/evaluate.py
```

## 说明
本任务唯一要求的运行入口是 `verification/evaluate.py`。
