# 可微全息 H1 规范：多焦点相对光强配比控制

## 工程背景

你可以把这个任务理解为“物理版图像生成器”：

- 输入：一束激光（2D 场）。
- 可训练参数：若干相位掩模层。
- 输出：某个观测平面的强度图。

目标是：在输出面上形成 **6 个亮点**，且亮点之间的相对亮度满足指定比例。

工程意义：

- 并行激光加工（一次打多个点），
- 光镊多陷阱控制，
- 多通道光耦合。

经济价值：

- 更高能量利用率和更准的分配，可提升产线效率与良率。

## 你要做的事

你需要改进 baseline 的优化策略，使其分数更高。

任务约束：

- 允许修改：`baseline/init.py`
- `verification/` 下评测和 oracle 视为只读。

## 核心修改文件/函数

主要修改点：

- `baseline/init.py`
- 核心函数：`solve(spec, device=None, seed=0)`

你可以改同文件内辅助函数，但必须保持返回字段与 evaluator 兼容。

## 输入协议（`spec`）

`verification/evaluate.py` 会基于 `make_default_spec()` 构造 `spec`，并注入评测常量。

关键字段：

- `shape`：仿真网格大小（如 72 表示 72x72）。
- `spacing`：采样间距（米/像素）。
- `wavelength`：波长。
- `waist_radius`：输入高斯光束腰半径。
- `layer_z`：可训练相位层的 z 位置。
- `output_z`：输出观测面位置。
- `focus_centers`：6 个目标焦点坐标 `(x, y)`（米）。
- `focus_ratios`：目标焦点功率比例。
- `roi_radius_m`：统计焦点功率的 ROI 半径。

评测注入参数：

- `score_eff_target`, `score_ratio_scale`
- `valid_ratio_mae_max`, `valid_efficiency_min`, `valid_score_min`
- `better_score_margin`, `better_shape_margin`

## 输出协议（`solve` 返回）

`solve` 至少返回以下键：

- `system`：训练后的光学系统（评测会用它继续传播）。
- `input_field`：输入光场。
- `target_field`：目标模板场/强度。
- `loss_history`：训练损失曲线。
- `spec`（建议保留）：运行时使用的配置。

缺失这些键或几何不匹配会导致评测失败。

## Baseline 当前实现

当前 baseline 有意简化：

1. 构造高斯输入光。
2. 用 6 个高斯斑点（按目标比例加权）构造目标场。
3. 只优化重叠损失：
   - `loss = 1 - |<output, target>|^2`
4. Adam 固定步数训练。

设计弱点：

- 没有直接优化配比误差，
- 没有显式惩罚泄露，
- 没有分阶段优化策略。

## Oracle 当前实现

`verification/reference_solver.py` 更强，允许第三方库：

1. 先用 `slmsuite` 的 WGS 生成高质量相位初值。
2. 将初值注入系统层。
3. 用复合目标微调：
   - 重叠项，
   - 配比误差项，
   - 泄露项，
   - 相位平滑正则。

它是工程上更强的参考解，不是 baseline。

## 指标与分数（0~1，越高越好）

在输出强度上计算：

- `ratio_mae`：焦点配比 MAE。
- `efficiency`：所有焦点 ROI 内能量占总能量比例。
- `shape_cosine`：预测与目标归一化强度图余弦相似度。

派生分项：

- `ratio_score = exp(-ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, efficiency / score_eff_target)`

最终分数：

- `score = (efficiency_score^0.58) * (ratio_score^0.22) * (shape_cosine^0.20)`

解释：

- 接近 `1.0`：效率高、配比准、形状像目标；
- `0.2~0.4`：部分可用，但明显有短板；
- 接近 `0`：基本没有实现目标。

## valid 与 better 规则

`baseline valid=True` 需要同时满足：

- `ratio_mae <= valid_ratio_mae_max`
- `efficiency >= valid_efficiency_min`
- `score >= valid_score_min`

`reference better_than_baseline=True` 需要同时满足：

- `reference_score >= baseline_score + better_score_margin`
- `reference_shape_cosine >= baseline_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

`verification/evaluate.py` 会写入 `verification/artifacts/`：

- `summary.json`
  - 机器可读总结果，
  - 包含 spec、耗时、各项指标、总分、valid 与对比结论。
- `intensity_maps.png`
  - 目标图 / baseline 输出 / reference 输出并排图，
  - 用于快速看“位置对不对、形状像不像”。
- `ratios_and_losses.png`
  - 焦点功率比例柱状图（目标 vs baseline vs reference），
  - 训练 loss 曲线。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py --device cpu
```

可选参数：

- `--seed`
- `--baseline-steps`
- `--reference-steps`
- `--artifacts-dir`

