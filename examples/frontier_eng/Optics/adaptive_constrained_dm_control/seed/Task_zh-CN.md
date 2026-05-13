# 自适应光学 A1 说明：受约束 DM 控制

## 领域背景

你可以把这个任务看成一个**带硬约束的向量优化控制问题**。

- 系统真实状态是光学波前畸变（相位误差）。
- 传感器输出是斜率向量 `s`（WFS slopes）。
- 控制器要输出执行器命令 `u`（DM 电压）。
- 每个执行器有物理边界：`u_i` 必须在 `[-Vmax, Vmax]`。

如果只做 `u = R @ s` 再 `clip`，虽然合法，但在硬约束下通常不是最优。

## 你需要做什么

只修改**一个函数**，实现更好的控制策略：

- 可编辑文件：`baseline/init.py`
- 目标函数：

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands=None, max_voltage=0.15):
    ...
```

目标：
- 提高排行榜分数 `score_0_to_1_higher_is_better`。
- 保持输出始终 valid（形状正确、数值有限、不越界）。



### 输入

- `slopes: np.ndarray`，形状 `(2 * n_subap,)`
  - 当前帧 WFS 斜率观测。
- `reconstructor: np.ndarray`，形状 `(n_act, 2 * n_subap)`
  - baseline 线性重建矩阵。
- `control_model: dict`
  - 由 `verification/evaluate.py` 预计算并传入。
  - 常用字段包括：
    - `normal_matrix`: `H^T H + lambda I`
    - `h_t`: `H^T`
    - `h_matrix`: `H`
    - `pgd_step`, `pgd_iters`
    - `ridge_design_matrix`: 增广矩阵 `[H; sqrt(beta) I]`
    - `ridge_rhs_zeros`: 增广目标的零向量尾部
    - `lag_comp_gain`: 延迟补偿增益
- `prev_commands: np.ndarray | None`，形状 `(n_act,)`
  - 上一帧已执行命令（可用于延迟补偿）。
- `max_voltage: float`
  - 每个执行器的电压上限。

### 输出

- `dm_commands: np.ndarray`，形状 `(n_act,)`
  - 必须满足：
    - 形状正确
    - 不含 NaN/Inf
    - 所有元素在 `[-max_voltage, max_voltage]`

## Verification 场景

`verification/evaluate.py` 构造了带工程噪声和失配的动态基准：

1. 时间相关的低阶湍流模态。
2. 小幅高阶扰动。
3. 斜率观测延迟 + 噪声。
4. 执行器滞后（`ACTUATOR_LAG`），命令不会瞬时生效。
5. 名义模型与真实 DM 存在增益失配。

因此，任务不是静态矩阵乘法，而是动态闭环中的受约束控制。

## 指标与分数（0~1，越高越好）

排行榜核心分数字段：
- `score_0_to_1_higher_is_better`，范围 `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

`metrics.json` 的原始指标：
- `mean_rms`：残差 RMS 平均值（越低越好）
- `worst_rms`：最差残差 RMS（越低越好）
- `mean_strehl`：成像质量代理（越高越好）
- `mean_saturation_ratio`：达到电压边界的比例（越低越好）

分数由 utility 加权聚合：
- `0.20 * U(mean_rms)`
- `0.10 * U(worst_rms)`
- `0.15 * U(mean_strehl)`
- `0.55 * U(mean_saturation_ratio)`

锚点（来自评测器）：
- 越低越好：
  - `mean_rms`: good `1.35`, bad `2.10`
  - `worst_rms`: good `2.10`, bad `3.10`
  - `mean_saturation_ratio`: good `0.02`, bad `0.35`
- 越高越好：
  - `mean_strehl`: good `0.24`, bad `0.08`

`raw_cost_lower_is_better` 只用于诊断，不是排行榜优化方向。

## Baseline 实现

`baseline/init.py` 目前做两步：
1. `u = reconstructor @ slopes`
2. 对 `u` 执行硬裁剪 `clip`

## 参考实现

`verification/reference_controller.py` 使用 SciPy 第三方求解器：
- `scipy.optimize.lsq_linear`
- 求解带边界的 ridge 最小二乘：
  - 最小化 `||H u - s||^2 + beta ||u||^2`
  - 约束 `u_i in [-Vmax, Vmax]`
- 并结合 `prev_commands` + `h_matrix` 做延迟补偿

它是刻意设置的强基准：
- 直接处理约束优化，而不是“先解再裁剪”。
- 依赖成熟外部求解器，更接近可验证的高质量参考。

## 文件说明

运行：

```bash
python verification/evaluate.py
```

会在 `verification/outputs/` 生成：

- `metrics.json`
  - 机器可读总结果（candidate baseline 与 reference 对比）。
  - 含分数、原始指标、评测配置、锚点与权重。
  - 适合作为排行榜或自动回归输入。
- `metrics_comparison.png`
  - 关键指标柱状图对比（baseline vs reference）。
  - 快速判断优化方向是否正确。
- `example_visualization.png`
  - 代表样本可视化：
    - 输入 phase
    - 校正后 residual
    - `log10(PSF)`
  - 用于核对“分数提升”是否对应物理上更合理的补偿。

## 依赖与约束策略

- 参考实现 verification/reference_controller.py使用了第三方 SciPy用于提供参考结果
- agent 修改 baseline/init.py 不允许调用此类外部库直接求解
