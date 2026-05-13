# 任务 02 - 通用多级库存优化（MEIO）

## 背景
这是一个带随机需求的网络优化问题。

- 图结构：5 节点 DAG（`10 -> {20,30} -> {40,50}`）
- 决策变量：每个节点的 base-stock 水平
- 目标：在随机需求下平衡成本与服务
- 约束：两个需求端不能出现明显服务失衡

## 工程场景
两层分销网络服务两个市场。

- 节点 40 和 50 直接面对外部需求
- 需求服从泊松分布，压力场景按 `x1.2` 放大
- 你要设计一个策略，同时兼顾成本、服务、鲁棒性与需求端公平性

## 输入
输入都在任务代码中定义，统一由 `verification/evaluate.py` 调用。

- 网络结构、提前期、成本参数：[`verification/evaluate.py`](verification/evaluate.py)
- baseline/reference 策略生成：
  - baseline：[`baseline/init.py`](baseline/init.py)
  - 参考解（stockpyl）：[`verification/reference.py`](verification/reference.py)
- 仿真配置：
  - 常规：`demand_scale=1.0`，`periods=160`，`seed=11`
  - 压力：`demand_scale=1.2`，`periods=160`，`seed=17`

## 输出
运行评测后生成：

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## 评分方式（0 到 1）
`clip(x) = min(1, max(0, x))`

- `CostScore`（0.30）：常规场景单位时间成本下降
- `ServiceScore`（0.35）：常规场景加权 fill-rate 达标（`0.98 -> 0.995`）
- `RobustnessScore`（0.25）：压力场景单位时间成本下降
- `BalanceScore`（0.10）：两个需求端 fill-rate 平衡度（`|fill40-fill50|`）

总分：

`FinalScore = 0.30*CostScore + 0.35*ServiceScore + 0.25*RobustnessScore + 0.10*BalanceScore`

## 算法对应关系
Baseline（`baseline/init.py`，不调用 stockpyl 优化器）：

- 实现方式：手工规则/启发式实现，不调用 stockpyl 优化求解器。
- 输入输出：通过 `solve(...)` 输出任务策略参数（如 CST、base-stock、(s,S)、Q 等），供 `verification/evaluate.py` 统一打分。

- 人工需求覆盖启发式
- 通过下游均值与上游聚合倍数手工设定 base-stock

Reference（`verification/reference.py`，调用 stockpyl）：

- 实现方式：调用 stockpyl 对应模型的优化/动态规划/枚举/启发式 API 求解。
- 输入输出：同样通过 `solve(...)` 输出与 baseline 同结构的策略对象，确保评测过程可直接对比。

- `stockpyl.meio_general.meio_by_enumeration`
- 带分组约束的 MEIO 枚举优化

Evaluator（`verification/evaluate.py`）：

- 直接调用 baseline 与 reference
- 用同一仿真配置（`stockpyl.sim.simulation`）评估两种策略
- 输出指标、总分与对比结果

## 运行方式
```bash
cd tasks/general_meio
python verification/evaluate.py
```

## 说明
本任务唯一要求的运行入口是 `verification/evaluate.py`。
