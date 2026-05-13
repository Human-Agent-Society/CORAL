# 任务 05 - 供应中断下的 EOQ 优化（EOQD）

## 背景
这是一个带中断风险的单变量优化问题。

- 决策变量：订货量 `Q`
- 目标：最小化考虑中断后的期望成本
- 权衡：`Q` 大可降低下单频率风险，但会提升持有成本

## 工程场景
采购方从一个易中断供应商采购关键物料。

- 供应状态在“中断/恢复”之间随机切换
- 需求高且持续
- 你需要选一个 `Q`，在模型成本和仿真服务/风险指标上都表现较好

## 输入
输入定义在 `verification/evaluate.py`，并传递给两种方法。

- 成本与中断参数：[`verification/evaluate.py`](verification/evaluate.py)
- baseline 生成器：[`baseline/init.py`](baseline/init.py)
- stockpyl 参考生成器：[`verification/reference.py`](verification/reference.py)

## 输出
运行评测后生成：

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## 评分方式（0 到 1）
`clip(x) = min(1, max(0, x))`

- `CostScore`（0.35）：相对基线 `Q` 的模型成本下降（`EOQD cost`）
- `ServiceScore`（0.35）：仿真 fill-rate 达标（`0.25 -> 0.60`）
- `RiskScore`（0.25）：仿真缺货事件率下降
- `CapitalScore`（0.05）：平均在库越低越好

总分：

`FinalScore = 0.35*CostScore + 0.35*ServiceScore + 0.25*RiskScore + 0.05*CapitalScore`

## 算法对应关系
Baseline（`baseline/init.py`，不调用 stockpyl 优化器）：

- 实现方式：手工规则/启发式实现，不调用 stockpyl 优化求解器。
- 输入输出：通过 `solve(...)` 输出任务策略参数（如 CST、base-stock、(s,S)、Q 等），供 `verification/evaluate.py` 统一打分。

- 先算经典 EOQ：`sqrt(2KD/h)`
- 再加人工中断安全系数：`Q_manual = Q_classic * (1 + 0.5*lambda/mu)`

Reference（`verification/reference.py`，调用 stockpyl）：

- 实现方式：调用 stockpyl 对应模型的优化/动态规划/枚举/启发式 API 求解。
- 输入输出：同样通过 `solve(...)` 输出与 baseline 同结构的策略对象，确保评测过程可直接对比。

- `stockpyl.supply_uncertainty.eoq_with_disruptions`
- 在中断率与恢复率约束下优化 EOQD

Evaluator（`verification/evaluate.py`）：

- 直接调用 baseline 与 reference
- 用 `eoq_with_disruptions_cost` 计算模型成本指标
- 用自定义随机仿真计算 fill-rate、缺货事件率、平均在库

## 运行方式
```bash
cd tasks/disruption_eoqd
python verification/evaluate.py
```

## 说明
本任务唯一要求的运行入口是 `verification/evaluate.py`。
