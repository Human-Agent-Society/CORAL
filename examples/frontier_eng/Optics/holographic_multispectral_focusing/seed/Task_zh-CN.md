# 可微全息 H3 规范：多波长聚焦/分束

## 工程背景

不同波长（可理解为不同颜色）传播行为不同。

很多真实系统要求“同一个器件”同时满足多波长目标：

- 每个波长到自己的空间位置，
- 多波长总体功率分配要满足指定比例。

从 CS 角度看，这是多域联合优化：

- 域 = 波长，
- 每个域有自己的空间目标，
- 还有全局耦合约束（光谱比例）。

应用：

- 彩色成像光学，
- WDM 波分路由，
- 色差补偿。

经济意义：

- 多波长性能更好，可在不增加硬件通道的前提下提升成像/传输品质。

## 你要做的事

改进 `baseline/init.py` 的优化流程，在共享硬件约束下提升分数。

可编辑：

- `baseline/init.py`

挑战中通常只读：

- `verification/evaluate.py`
- `verification/reference_solver.py`

## 核心修改文件/函数

主函数：

- `baseline/init.py` 的 `solve(spec, device=None, seed=0)`

保持返回字段不变。

## 输入协议（`spec`）

关键字段：

- `wavelengths`：波长列表。
- `target_centers`：每个波长对应一个目标坐标。
- `target_spectral_ratios`：多波长目标功率比例。
- 光学几何：`shape`, `spacing`, `layer_z`, `output_z`, `waist_radius`。
- `roi_radius_m`：能量统计 ROI 半径。

评测注入参数：

- `score_eff_target`, `score_spectral_scale`，
- `valid_*` 阈值，
- reference 对比 margin。

## 输出协议（`solve` 返回）

至少返回：

- `system`：共享光学系统。
- `input_fields`：每个波长一个输入场。
- `loss_history`。
- `spec`（建议）。

评测会把每个波长输入都通过返回的系统计算指标。

## Baseline 当前实现

baseline 目前刻意简化：

1. 构造共享多波长相位系统。
2. 每个波长只优化目标 ROI 效率。
3. 各波长损失取平均。

刻意缺失：

- 不显式抑制串扰，
- 不显式约束光谱比例，
- 无高级初始化。

## Oracle 当前实现

reference 更强，且硬件约束更宽松：

1. 每个波长用 `slmsuite` WGS 生成相位初值。
2. 构建两个候选：
   - 直接按波长独立相位执行，
   - 按波长独立相位再微调。
3. 选任务分数更高的候选。

因为允许波长特定相位（而非严格共享掩模），它是上界对照解。

## 指标与分数（0~1）

每个波长 `i`：

- `target_efficiency_i = P_target_i / P_total_i`
- `designated_crosstalk_i = P_other_designated_i / (P_target_i + P_other_designated_i)`
- `shape_cosine_i = cosine(I_pred_norm_i, I_target_norm_i)`

全局：

- `mean_target_efficiency`
- `mean_crosstalk`
- `mean_shape_cosine`
- `spectral_ratio_mae`

派生分项：

- `efficiency_score = min(1, mean_target_efficiency / score_eff_target)`
- `isolation_score = 1 - mean_crosstalk`
- `spectral_score = exp(-spectral_ratio_mae / score_spectral_scale)`

最终分数：

- `mean_score = (efficiency_score^0.45) * (isolation_score^0.25) * (spectral_score^0.20) * (mean_shape_cosine^0.10)`

解释：

- 高分必须同时满足空间目标和光谱目标，
- 单一维度很好、另一维度很差，最终也拿不到高分。

## valid 与 better 规则

`baseline valid=True` 需满足：

- `mean_target_efficiency >= valid_mean_target_efficiency_min`
- `mean_crosstalk <= valid_mean_crosstalk_max`
- `mean_score >= valid_mean_score_min`

`reference better_than_baseline=True` 需满足：

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## 评测输出文件说明（artifacts）

输出目录：`verification/artifacts/`

- `summary.json`
  - 完整指标、分数、耗时、判定结果。
- `spectral_intensity_maps.png`
  - 每个波长的 target / baseline / reference 强度图。
- `loss_and_spectral_ratios.png`
  - 训练 loss 曲线，
  - 光谱比例柱状图（目标 vs baseline vs reference）。

排查建议：

- 光谱比例差：加强 ratio/spectral loss，
- 串扰高：加强 designated-vs-other 抑制项，
- shape cosine 低：改初始化或优化权重平衡。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multispectral_focusing/verification/evaluate.py --device cpu
```

