# 任务 02 说明：CVaR 压力控制配置

## 背景

你要在情景收益数据上做多头资产配置。
PM 要求组合达到最低预期收益，风控要求控制尾部亏损，因此目标是：
在约束下最小化 CVaR。

## 输入

`instance` 字段：
- `scenario_returns`: `np.ndarray`，形状 `(T, N)`
- `mu`: `np.ndarray`，形状 `(N,)`，预期收益估计
- `w_prev`: `np.ndarray`，形状 `(N,)`
- `lower`: `np.ndarray`，形状 `(N,)`
- `upper`: `np.ndarray`，形状 `(N,)`
- `sector_ids`: `np.ndarray`，形状 `(N,)`
- `sector_lower`: `dict[int, float]`
- `sector_upper`: `dict[int, float]`
- `beta`: `float`，CVaR 置信度
- `target_return`: `float`，最低收益门槛
- `turnover_limit`: `float`，`||w - w_prev||_1` 上限

## 输出

返回：
- `weights`: `np.ndarray`，形状 `(N,)`

## 优化目标与约束

最小化场景损失的 CVaR：
- 第 `t` 个场景损失：`L_t = -R_t^T w`
- `CVaR_beta = alpha + 1/((1-beta)T) * sum_t u_t`
- 且 `u_t >= L_t - alpha`，`u_t >= 0`

约束：
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- `mu^T w >= target_return`
- 行业上下界约束
- `||w - w_prev||_1 <= turnover_limit`

## 预期结果

高质量解应在满足约束前提下，把尾部风险压到接近最优。

## 计分方式

每个样本：
1. 参考实现得到最优 CVaR：`c_ref`；
2. 提交解 CVaR：`c_cand`；
3. 取等权组合 CVaR 作为锚点：`c_anchor`；
4. 归一化改进：
   - `norm = (c_anchor - c_cand) / (c_anchor - c_ref + 1e-12)`
5. 计算约束违约惩罚 penalty；
6. 得分：
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

最终分数为所有样本平均。

## 理论上限

该形式是凸优化，参考实现（CVXPY）给出的最优值可视为本任务定义下理论上限，
对应得分 100。

## 实现建议

不调用现成优化器时可从启发式出发：
- 用最差场景估计单资产尾部风险；
- 构造 `mu / tail_risk` 风险收益打分；
- 生成初始权重并做约束修复；
- 若未达到收益门槛，贪心向高收益资产挪仓。

该方法不是全局最优，但足够用于 baseline。
