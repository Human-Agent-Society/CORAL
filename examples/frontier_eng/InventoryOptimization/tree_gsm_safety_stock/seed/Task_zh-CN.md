# 任务 01 - 树形供应链战略安全库存配置（GSM 动态规划）

## 背景
把这个任务看成一个带约束的树图优化问题。

- 图结构：`1 -> 3 -> {2,4}`
- 决策变量：每个节点的承诺服务时间（CST）
- 目标：最小化期望库存相关成本
- 约束：需求节点必须满足 SLA 上限

## 工程场景
一个工厂通过中间节点向两个市场供货。

- 节点 2：高优先级市场（严格 SLA，`CST <= 0`）
- 节点 4：普通市场（`CST <= 1`）
- 压力场景：需求波动标准差提高 30%

你需要得到一个在常规场景和压力场景都稳健的 CST 策略。

## 输入
输入由任务代码定义，统一由 `verification/evaluate.py` 读取。

- 树结构、成本、处理时间、CST 约束（stockpyl 模型构建）：[`verification/reference.py`](verification/reference.py)
- 压力测试参数（`demand_scale=1.3`）和评分阈值：[`verification/evaluate.py`](verification/evaluate.py)
- 对照基线策略：`{1:0, 3:0, 2:0, 4:0}`

## 输出
运行评测后会生成：

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## 评分方式（0 到 1）
`clip(x) = min(1, max(0, x))`

- `CostScore`（0.35）：常规场景相对基线的降本幅度
- `RobustnessScore`（0.35）：压力场景相对基线的降本幅度
- `SLACompliance`（0.10）：节点 2/4 的 SLA 满足情况
- `ComplexityScore`（0.20）：变更节点数 `<=1` 才满分

总分：

`FinalScore = 0.35*CostScore + 0.35*RobustnessScore + 0.10*SLACompliance + 0.20*ComplexityScore`

## 算法对应关系
Baseline（`baseline/init.py`，不调用 stockpyl 优化器）：

- 实现方式：手工规则/启发式实现，不调用 stockpyl 优化求解器。
- 输入输出：通过 `solve(...)` 输出任务策略参数（如 CST、base-stock、(s,S)、Q 等），供 `verification/evaluate.py` 统一打分。

- 规则式 CST 分配
- 需求节点按 SLA 固定：节点 2 -> 0，节点 4 -> 1
- 内部节点按处理时间阈值：`processing_time >= 2 => CST=1`，否则 `0`

Reference（`verification/reference.py`，调用 stockpyl）：

- 实现方式：调用 stockpyl 对应模型的优化/动态规划/枚举/启发式 API 求解。
- 输入输出：同样通过 `solve(...)` 输出与 baseline 同结构的策略对象，确保评测过程可直接对比。

- `stockpyl.gsm_tree.optimize_committed_service_times`
- GSM 树形网络动态规划优化 CST

Evaluator（`verification/evaluate.py`）：

- 直接调用 baseline 和 reference
- 用 `stockpyl.gsm_helpers.solution_cost_from_cst` 做统一成本评估
- 输出两种方法结果和最终对比

## 运行方式
```bash
cd tasks/tree_gsm_safety_stock
python verification/evaluate.py
```

## 说明
本任务唯一要求的运行入口是 `verification/evaluate.py`。
