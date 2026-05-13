# 任务 01 说明：鲁棒 MVO 再平衡

## 背景

你在实现一个股票组合再平衡器。
策略给出预期收益 `mu` 和协方差 `Sigma`，但风控和交易要求还要满足：
- 个股仓位上下界，
- 行业暴露上下界，
- 风格/因子暴露上下界，
- 相对当前持仓的换手上限，
- L1 交易惩罚。

这是一个带约束的凸优化问题。

## 输入

求解器接收一个 Python `dict`（命名为 `instance`）：

- `mu`: `np.ndarray`，形状 `(N,)`，预期收益。
- `cov`: `np.ndarray`，形状 `(N, N)`，半正定协方差矩阵。
- `w_prev`: `np.ndarray`，形状 `(N,)`，当前组合权重。
- `lower`: `np.ndarray`，形状 `(N,)`，下界。
- `upper`: `np.ndarray`，形状 `(N,)`，上界。
- `sector_ids`: `np.ndarray`，形状 `(N,)`，每个资产所属行业 id。
- `sector_lower`: `dict[int, float]`，行业下界。
- `sector_upper`: `dict[int, float]`，行业上界。
- `factor_loadings`: `np.ndarray`，形状 `(N, K)`，资产对 K 个风险因子的暴露矩阵。
- `factor_lower`: `np.ndarray`，形状 `(K,)`，组合因子暴露下界。
- `factor_upper`: `np.ndarray`，形状 `(K,)`，组合因子暴露上界。
- `risk_aversion`: `float`，风险厌恶系数。
- `transaction_penalty`: `float`，交易惩罚系数。
- `turnover_limit`: `float`，L1 换手上限。

## 输出

返回 `dict`，至少包含：
- `weights`: `np.ndarray`，形状 `(N,)`。

其他字段评测器会忽略。

## 优化目标与约束

最大化：

`mu^T w - risk_aversion * w^T cov w - transaction_penalty * ||w - w_prev||_1`

约束：
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- 行业约束：
  - `sector_lower[s] <= sum_{i in sector s} w_i <= sector_upper[s]`
- 因子暴露约束：
  - `factor_lower[k] <= sum_i factor_loadings[i, k] * w_i <= factor_upper[k]`
- 换手约束：
  - `||w - w_prev||_1 <= turnover_limit`

## 预期结果

高质量解应满足：
- 数值容差内可行；
- 目标值尽量接近凸优化最优值。

## 计分方式

每个测试样本：
1. 计算参考最优目标值 `f_ref`；
2. 计算提交解目标值 `f_cand`；
3. 采用朴素锚点做归一化：
   - `f_anchor = min(f_uniform, f_prev_holdings)`
   - `norm = (f_cand - f_anchor) / (f_ref - f_anchor + 1e-12)`
4. 计算可行性惩罚：
   - 每类约束违约计入 penalty，最终裁剪到 `[0, 1]`；
5. 样本得分：
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

最终得分是所有样本平均值。

## 理论上限

该问题是凸优化，参考实现（CVXPY 全局最优）可视为本任务定义下的理论上限，
对应得分 `100`。

## 实现建议

不依赖现成优化器的 baseline 可采用：
- 平滑目标 + 投影梯度上升；
- 迭代修复约束：
  - 先按个股上下界截断；
  - 再通过缩放 `w - w_prev` 控制换手；
  - 对行业超限做比例回收/补足；
  - 最后归一化到 `sum(w)=1`。

这种方法通常不是全局最优，但可作为可运行起点。

## 本仓库 Baseline 实现方式

- 文件：`baseline/init.py`
- 方法类型：一阶启发式（不调用外部优化器）
- 核心做法：
  - 对 L1 项做平滑后进行梯度上升，
  - 每轮迭代后对权重进行“修复/投影”，满足仓位边界、行业约束、换手与权重和约束。
- 特点：
  - 速度快、依赖少；
  - 不显式投影到因子暴露约束；
  - 不保证全局最优。

## 本仓库 Reference 实现方式

- 文件：`verification/reference.py`
- 方法类型：CVXPY 精确凸优化
- 核心做法：
  - 将目标函数与全部约束一次性建模求解，
  - 显式包含个股/行业/因子/换手约束。
- 特点：
  - 返回该问题定义下的最优（或 `optimal_inaccurate` 时近最优）解；
  - 作为评测上限使用。
