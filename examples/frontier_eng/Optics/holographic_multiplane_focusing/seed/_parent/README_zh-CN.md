# 光学任务集（16个子任务）

## 共同背景

这 16 个任务覆盖四类真实光学优化场景：

- 自适应光学波前控制与鲁棒融合，
- 纯相位 DOE / 全息配光，
- 光纤通信资源调度，
- 可微衍射光学多条件设计（空间/深度/光谱/偏振）。

任务大致分为四组，并采用语义前缀：

- `adaptive_*`：自适应光学控制类
- `phase_*`：相位 DOE 类
- `fiber_*`：光通信资源调度类
- `holographic_*`：可微全息设计类

## 子任务差异

| 任务目录 | 核心优化目标 | 典型难点/约束 |
|---|---|---|
| `adaptive_constrained_dm_control` | 有界 DM 控制质量 | 执行器电压约束 + 延迟噪声 |
| `adaptive_temporal_smooth_control` | 时序平滑与补偿效果折中 | 抖动/滞后/动态约束 |
| `adaptive_energy_aware_control` | 补偿效果与能耗折中 | 稀疏低能控制 |
| `adaptive_fault_tolerant_fusion` | 多 WFS 鲁棒融合 | 通道污染与异常值抑制 |
| `phase_weighted_multispot_single_plane` | 单平面多焦点加权配光 | 相位非凸优化 |
| `phase_fourier_pattern_holography` | 稀疏高对比图案重建 | 结构保真与暗区泄漏折中 |
| `phase_dammann_uniform_orders` | Dammann 跃迁参数优化 | 级次均匀性与效率平衡 |
| `phase_large_scale_weighted_spot_array` | 大规模(8x8)加权焦点阵列 | 多目标稳定分配 |
| `fiber_wdm_channel_power_allocation` | 用户-信道映射与功率分配 | 串扰耦合与总功率预算 |
| `fiber_mcs_power_scheduling` | `(MCS, 功率)` 联合调度 | 多选背包式预算优化 |
| `fiber_dsp_mode_scheduling` | EDC/DBP 模式调度 | 时延预算下的效用折中 |
| `fiber_guardband_spectrum_packing` | 频谱区间打包 | 不重叠与保护带几何约束 |
| `holographic_multifocus_power_ratio` | 单平面多焦点功率比控制 | 焦点质量与比例精度 |
| `holographic_multiplane_focusing` | 单设计多深度聚焦 | 多平面一致性 |
| `holographic_multispectral_focusing` | 多波长路由与光谱配比 | 波长耦合与串扰 |
| `holographic_polarization_multiplexing` | 偏振复用通道分离 | 交叉偏振泄漏抑制 |

## 分数与输出说明

不同任务族的打分字段略有差异（例如 `score_0_to_1_higher_is_better`、`score_pct`），但方向统一为 **分数越高越好**。

## 环境依赖

```bash
python -m pip install -r benchmarks/Optics/requirements.txt
```

## 快速运行示例

```bash
python benchmarks/Optics/adaptive_constrained_dm_control/verification/evaluate.py
python benchmarks/Optics/phase_weighted_multispot_single_plane/verification/validate.py
python benchmarks/Optics/fiber_wdm_channel_power_allocation/verification/run_validation.py
python benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py
```

## Frontier Eval（Unified）

16 个 Optics 子任务都已通过 `task=unified` 接入 `frontier_eval`，每个任务目录下都有对应元数据（`benchmarks/Optics/<task>/frontier_eval`）。

示例：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Optics/phase_weighted_multispot_single_plane \
  algorithm=openevolve \
  algorithm.iterations=0
```

将 `task.benchmark` 替换为本 README 中任一任务目录即可。

## 超时与耗时参考

在 `frontier_eval` 中，单次评测默认超时是 `300s`。

- OpenEvolve：`algorithm.oe.evaluator.timeout=300`（默认）
- ABMCTS / ShinkaEvolve：`algorithm.evaluator_timeout_s=300`（默认）

如果出现超时（尤其是 `holographic_*`），可以提高上限：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Optics/holographic_multifocus_power_ratio \
  algorithm=openevolve \
  algorithm.iterations=0 \
  algorithm.oe.evaluator.timeout=600
```

大概耗时（单次评测、`algorithm.iterations=0`、CPU）：

| 任务族 | 大概耗时 |
|---|---|
| `adaptive_*` | ~`6-15s` |
| `phase_*` | ~`8-20s` |
| `fiber_*` | ~`7-20s` |
| `holographic_*` | ~`170-260s`（慢 CPU 可能超过 `300s`） |

代表性任务实测：
- `adaptive_constrained_dm_control`：~`6.3s`
- `phase_weighted_multispot_single_plane`：~`9.3s`
- `fiber_wdm_channel_power_allocation`：~`7.2s`
- `holographic_multifocus_power_ratio`：~`184.7s`
