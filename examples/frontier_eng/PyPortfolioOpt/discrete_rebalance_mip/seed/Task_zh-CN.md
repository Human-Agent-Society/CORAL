# 任务 03 说明：离散再平衡 MIP

## 背景

你的模型给出目标权重，但实际执行必须用整数手数下单。
同时还要满足交易费与换手金额限制。

这本质上是一个混合整数线性优化问题。

## 输入

`instance` 字段：
- `prices`: `np.ndarray`，形状 `(N,)`
- `lot_sizes`: `np.ndarray`，形状 `(N,)`，正整数
- `current_lots`: `np.ndarray`，形状 `(N,)`，当前整数手数
- `target_weights`: `np.ndarray`，形状 `(N,)`，和接近 1
- `portfolio_value`: `float`，最终持仓 + 手续费预算
- `fee_rate`: `float`，按成交金额收取比例费用
- `turnover_limit_value`: `float`，成交金额上限
- `max_lots`: `np.ndarray`，形状 `(N,)`，每个资产最大手数

定义每手金额：`unit_i = prices_i * lot_sizes_i`。

## 输出

返回：
- `lots`: `np.ndarray`，形状 `(N,)`，最终整数手数

其他字段评测器忽略。

## 优化目标与约束

最小化：

`sum_i |unit_i * lots_i - target_weights_i * portfolio_value| + fee_rate * traded_notional`

其中：

`traded_notional = sum_i unit_i * |lots_i - current_lots_i|`

约束：
- `0 <= lots_i <= max_lots_i`，且为整数
- `traded_notional <= turnover_limit_value`
- `sum_i unit_i * lots_i + fee_rate * traded_notional <= portfolio_value`

## 预期结果

高质量解应在可执行约束下尽量贴近目标权重（金额层面）。

## 计分方式

每个样本：
1. 参考整数最优目标 `obj_ref`；
2. 提交解目标 `obj_cand`；
3. 不交易（`current_lots`）目标作为锚点 `obj_anchor`；
4. 归一化：
   - `norm = (obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12)`
5. 施加可行性/整数性惩罚；
6. 得分：
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

最终分数是所有样本均值。

## 理论边界

- 实际评测上限：参考整数最优（100 分）。
- 额外理论对照：LP 松弛下界（连续手数），评测脚本会同时输出用于分析整数间隙。

## 实现建议

不调用外部求解器时可采用：
- 按目标金额四舍五入初始化；
- 对预算/换手超限做修复循环；
- 通过 `+/-1` 手局部搜索改进目标；
- 在约束允许下贪心补足低配资产。

这是实务里常见的启发式工程方案。
