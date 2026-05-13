# 可微全息 H2 规范：多平面同时聚焦

## 工程背景

任务1是单平面。任务2引入了**深度维度**。

你需要一个统一的光学系统，在多个 `z` 距离上同时满足不同目标图样：

- 硬件参数相同，
- 不同深度有不同目标焦点和配比。

可类比为“一个模型同时服务多个切片视图”。

应用场景：

- 3D 光镊，
- 体加工，
- 多深度投影。

经济意义：

- 一个器件完成多深度功能，可降低系统复杂度与标定成本。

## 你要做的事

改进 baseline 的优化流程，让它在多平面指标上更好。

可编辑：

- `baseline/init.py`

挑战中通常只读：

- `verification/evaluate.py`
- `verification/reference_solver.py`

## 核心修改文件/函数

主要函数：

- `baseline/init.py`
- `solve(spec, device=None, seed=0)`

保持返回字段与 evaluator 兼容。

## 输入协议（`spec`）

主要字段：

- 全局光学配置：
  - `shape`, `spacing`, `wavelength`, `waist_radius`, `layer_z`
- `planes`：平面配置列表，每个平面包含：
  - `z`：输出面深度，
  - `centers`：目标焦点坐标，
  - `ratios`：该平面的目标功率配比。
- `roi_radius_m`：统计焦点功率的 ROI 半径。

评测还会注入：

- 评分参数 `score_eff_target`, `score_ratio_scale`，
- valid 阈值，
- reference 对比 margin。

## 输出协议（`solve` 返回）

至少包含：

- `system`
- `input_field`
- `target_fields`（每个平面一个）
- `loss_history`
- `spec`（建议）

评测会对每个平面调用 `system.measure_at_z(input_field, z=plane_z)`。

## Baseline 当前实现

baseline 目前刻意偏弱：

1. 构造一个输入高斯场。
2. 为每个平面构造目标场。
3. 计算各平面重叠损失。
4. 平均后用 Adam 优化。

不足：

- 不直接优化配比，
- 不直接控制泄露/效率，
- 没有针对困难平面的动态加权。

## Oracle 当前实现

`verification/reference_solver.py` 更强：

1. 每个平面先用 `slmsuite` WGS 生成相位种子。
2. 将多个种子融合成多层初值。
3. 用复合目标微调：
   - 重叠项，
   - 配比项，
   - 泄露项。
4. 对困难平面动态加权。

该实现作为对照上界。

## 指标与分数（0~1）

对每个平面 `m` 计算：

- `ratio_mae_m`
- `efficiency_m = P_focus_m / P_total_m`
- `shape_cosine_m = cosine(I_pred_norm_m, I_target_norm_m)`

派生分项：

- `ratio_score_m = exp(-ratio_mae_m / score_ratio_scale)`
- `efficiency_score_m = min(1, efficiency_m / score_eff_target)`

平面分数：

- `score_m = (efficiency_score_m^0.50) * (ratio_score_m^0.35) * (shape_cosine_m^0.15)`

全局：

- `mean_ratio_mae`
- `mean_efficiency`
- `mean_shape_cosine`
- `mean_score = average(score_m)`

解释：

- 越接近 `1` 表示多平面同时满足得更好，
- 低分通常意味着某个平面严重拖后腿。

## valid 与 better 规则

`baseline valid=True` 需同时满足：

- `mean_ratio_mae <= valid_mean_ratio_mae_max`
- `mean_efficiency >= valid_mean_efficiency_min`
- `mean_score >= valid_mean_score_min`

`reference better_than_baseline=True` 需同时满足：

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 完整指标、配置、耗时、valid 与对比结论。
- `plane_intensity_maps.png`
  - 每个平面展示 target / baseline / reference 图。
- `loss_and_efficiency.png`
  - 训练损失曲线 + 各平面效率柱状图。

快速定位问题：

- 位置对但配比差：强化 ratio loss，
- 多平面都暗：强化能量集中/泄露控制，
- 只有一个平面差：做平面级加权或分阶段训练。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multiplane_focusing/verification/evaluate.py --device cpu
```

