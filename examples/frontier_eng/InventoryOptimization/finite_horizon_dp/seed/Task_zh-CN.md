# 任务 04 - 有限期随机库存控制（动态规划）

## 背景
这是一个有限期随机控制问题。

- 时域：8 个周期
- 状态：当前库存水平
- 动作：订货量（等价为 `(s_t, S_t)` 策略）
- 目标：在随机需求和期末惩罚下最小化期望总成本

## 工程场景
工厂在短周期内管理单 SKU，需求存在阶段性高峰。

- 各周期需求均值和方差都在变化
- 固定订货成本会惩罚频繁小批量下单
- 缺货惩罚高，但库存过高也有持有/资金占用成本

你需要构建一个随时间变化的策略来平衡这些目标。

## 输入
输入都定义在 `verification/evaluate.py`，并传入两种算法。

- 成本参数与需求曲线：[`verification/evaluate.py`](verification/evaluate.py)
- baseline 策略生成：[`baseline/init.py`](baseline/init.py)
- DP 参考策略生成：[`verification/reference.py`](verification/reference.py)

## 输出
运行评测后生成：

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## 评分方式（0 到 1）
`clip(x) = min(1, max(0, x))`

评分通过蒙特卡洛仿真计算（`1500` 次试验，固定随机种子保证可比性）。

- `CostScore`（0.55）：相对基线 order-up-to 策略的期望总成本下降
- `ServiceScore`（0.40）：平均 fill-rate 达标（`0.94 -> 0.975`）
- `CadenceScore`（0.05）：下单次数相对基线的下降幅度

总分：

`FinalScore = 0.55*CostScore + 0.40*ServiceScore + 0.05*CadenceScore`

## 算法对应关系
Baseline（`baseline/init.py`，不调用 stockpyl DP）：

- 实现方式：手工规则/启发式实现，不调用 stockpyl 优化求解器。
- 输入输出：通过 `solve(...)` 输出任务策略参数（如 CST、base-stock、(s,S)、Q 等），供 `verification/evaluate.py` 统一打分。

- 人工矩估计时变策略
- `s_t = round(0.60 * mean_t)`
- `S_t = max(round(mean_t + 1.10*sd_t + 32), s_t + 6)`

Reference（`verification/reference.py`，调用 stockpyl）：

- 实现方式：调用 stockpyl 对应模型的优化/动态规划/枚举/启发式 API 求解。
- 输入输出：同样通过 `solve(...)` 输出与 baseline 同结构的策略对象，确保评测过程可直接对比。

- `stockpyl.finite_horizon.finite_horizon_dp`
- 用动态规划求有限期最优 `(s,S)` 策略

Evaluator（`verification/evaluate.py`）：

- 直接调用 baseline 与 reference
- 在同一随机需求轨迹设定下仿真两种策略
- 输出分项指标、总分和对比

## 运行方式
```bash
cd tasks/finite_horizon_dp
python verification/evaluate.py
```

## 说明
本任务唯一要求的运行入口是 `verification/evaluate.py`。
