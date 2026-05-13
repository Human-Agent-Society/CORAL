# 可微全息 H4 规范：偏振复用

## 工程背景

偏振复用的核心是：同一个光学器件，对不同偏振输入产生不同输出功能。

本任务要求：

- x 偏振输入输出图样 X，
- y 偏振输入输出图样 Y，
- 并且两通道串扰要低。

CS 类比：

- 一个共享模型，
- 两种输入模式，
- 模式条件下输出要可控且可分离。

应用：

- 偏振复用通信，
- 光学安全，
- 多功能衍射/超表面器件。

经济意义：

- 一个器件多功能，可减少硬件数量与系统集成成本。

## 你要做的事

改进 baseline，使其在“通道分离 + 目标配比 + 有效能量”上更好。

可编辑：

- `baseline/init.py`

通常只读：

- `verification/evaluate.py`
- `verification/reference_solver.py`

## 核心修改文件/函数

主要修改：

- `baseline/init.py` 的 `solve(spec, device=None, seed=0)`

保持返回字段兼容。

## 输入协议（`spec`）

核心字段：

- 光学设置：
  - `shape`, `spacing`, `wavelength`, `layer_z`, `output_z`, `waist_radius`
- X 通道目标：
  - `pattern_x_centers`, `pattern_x_ratios`
- Y 通道目标：
  - `pattern_y_centers`, `pattern_y_ratios`
- `roi_radius_m`

评测会注入：

- 评分参数 `score_eff_target`, `score_ratio_scale`，
- valid 阈值，
- better 判定 margin。

## 输出协议（`solve` 返回）

至少返回：

- `output_field_x`, `output_field_y`
- `target_map_x`, `target_map_y`
- `loss_history`
- 以及评测依赖字段（`input_field_x`, `input_field_y`, `spec` 建议保留）

评测会直接读取这些字段计算指标。

## Baseline 当前实现

baseline 目前刻意简化：

1. 构造 x/y 偏振输入高斯场。
2. 用对角 Jones 相位层（Ex、Ey 各自独立相位）。
3. 仅优化两通道归一化图像 MSE。

缺失项：

- 没有显式串扰项，
- 没有显式配比项，
- 没有显式目标通道效率项。

## Oracle 当前实现

`verification/reference_solver.py` 更强：

1. 分别为 x/y 目标生成 `slmsuite` WGS 相位种子。
2. 用种子初始化偏振相位层。
3. 复合目标微调：
   - 图样匹配，
   - 串扰抑制，
   - 配比约束，
   - 目标通道效率，
   - 相位平滑正则。

作为工程上更强对照。

## 指标与分数（0~1）

核心指标：

- `match_x`, `match_y`, `mean_match`：与目标图余弦相似度。
- `separation_x`, `separation_y`, `separation`：通道分离度。
- `own_efficiency`：能量落在目标通道 ROI 的比例。
- `ratio_mae_x`, `ratio_mae_y`, `mean_ratio_mae`：通道内配比误差。

派生分项：

- `ratio_score = exp(-mean_ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, own_efficiency / score_eff_target)`

最终分数：

- `score = (separation^0.55) * (ratio_score^0.20) * (efficiency_score^0.25) * (mean_match^0.05)`

解释：

- 该分数更强调“通道分离”和“目标通道有效能量”，
- 图样相似度仍有作用，但权重较小。

## valid 与 better 规则

`baseline valid=True` 需满足：

- `mean_match >= valid_match_min`
- `separation >= valid_separation_min`
- `score >= valid_score_min`

`reference better_than_baseline=True` 需满足：

- `reference_score >= baseline_score + better_score_margin`
- `reference_separation >= baseline_separation + better_sep_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 全量结构化结果（指标、分数、耗时、判定）。
- `polarization_maps.png`
  - x/y 两个输入通道的 target / baseline / reference 对比图。
- `loss_and_metrics.png`
  - 训练 loss 曲线，
  - 指标柱状图（`match`, `separation`, `ratio_score`, `score`）。

快速排查：

- match 还行但 separation 低：串扰问题，
- separation 高但 ratio_score 低：通道内配比分配不对，
- efficiency_score 低：目标 ROI 内有效能量不足。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_polarization_multiplexing/verification/evaluate.py --device cpu
```

