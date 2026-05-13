# 自适应光学 A4 说明：故障容忍的多传感器融合

## 领域背景

这是一个**鲁棒估计 + 控制**问题。

输入来自多个传感器通道（`n_wfs` 路）。其中一部分通道会出现严重异常。如果直接做均值融合，异常值会主导融合结果，最终控制效果明显下降。

核心挑战是：**先做鲁棒融合，再做 DM 控制**。

## 你需要做什么

只修改一个函数：

- 文件：`baseline/init.py`
- 目标函数：

```python
def fuse_and_compute_dm_commands(slopes_multi, reconstructor, control_model, prev_commands=None, max_voltage=0.50):
    ...
```

目标：
- 在重故障场景下提升 `score_0_to_1_higher_is_better`。
- 保持输出始终 valid。



### 输入

- `slopes_multi: np.ndarray`，形状 `(n_wfs, 2 * n_subap)`
  - 每一路 WFS 对应一个斜率向量。
- `reconstructor: np.ndarray`，形状 `(n_act, 2 * n_subap)`
  - 将融合后斜率映射到 DM 命令的线性矩阵。
- `control_model: dict`
  - 可选鲁棒融合参数与辅助对象。
  - reference 路径会注入异常检测模型和融合超参数。
- `prev_commands: np.ndarray | None`，形状 `(n_act,)`
  - 可选上一帧命令。
- `max_voltage: float`
  - 电压边界。

### 输出

- `dm_commands: np.ndarray`，形状 `(n_act,)`
  - 必须有限且满足 `[-max_voltage, max_voltage]`。

## Verification 场景

`verification/evaluate.py` 构造故障主导的压力测试：

1. 先生成真实相位与干净斜率。
2. 构造 5 路 WFS 观测。
3. 每个样本随机污染 3 路，污染方式组合包括：
   - 增益失真，
   - 偏置/强噪声，
   - 稀疏尖峰，
   - 部分掉线。
4. 控制器仅能看到污染后的多路斜率。

该设置专门用来区分“鲁棒融合”和“简单平均”。

## 指标与分数（0~1，越高越好）

排行榜字段：
- `score_0_to_1_higher_is_better`，范围 `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

原始指标：
- `mean_rms`（越低越好）
- `p95_rms`（越低越好）
- `worst_rms`（越低越好，仅诊断）
- `mean_strehl`（越高越好）

utility 加权分数：
- `0.45 * U(mean_rms)`
- `0.35 * U(p95_rms)`
- `0.20 * U(mean_strehl)`

锚点：
- 越低越好：
  - `mean_rms`: good `0.95`, bad `1.75`
  - `p95_rms`: good `1.20`, bad `2.05`
- 越高越好：
  - `mean_strehl`: good `0.35`, bad `0.18`

`raw_cost_lower_is_better` 仅用于诊断分析。

## Baseline 实现

当前 baseline（`baseline/init.py`）：
1. `fused = mean(slopes_multi, axis=0)`
2. `u = reconstructor @ fused`
3. `clip` 到边界

弱点：
- 均值融合对异常值极其敏感，容易被坏通道拖垮。

## Oracle / Reference 实现

reference（`verification/reference_controller.py`）使用异常检测辅助融合：

- 第三方模型：`sklearn.ensemble.IsolationForest`
- 在评测器构造的干净斜率样本上训练
- 在线流程：
  - 计算每路传感器“正常性分数”
  - 保留分数最高的 inlier 通道
  - 用 softmax 风格权重做融合
  - 可选延迟/时间融合
  - 再线性控制 + clip

为什么更强：
- 它显式建模传感器异常，而不是默认所有通道同等可信。

## verification/outputs 文件作用

运行：

```bash
python verification/evaluate.py
```

会在 `verification/outputs/` 生成：

- `metrics.json`
  - baseline/reference 的结构化结果（分数、原始指标、评测元信息）。
  - 自动评分与可复现实验的核心文件。
- `metrics_comparison.png`
  - 分数与关键指标柱状图。
  - 快速查看鲁棒性是否提升。
- `example_visualization.png`
  - 代表样本的 phase/residual/PSF 对比图。
  - 用于确认指标收益是否对应可见残差改善。

## 依赖与约束策略

- Baseline 期望保持轻量（`numpy` + 给定矩阵）。
- Reference 允许使用第三方 `scikit-learn`（`IsolationForest`）。
- 不允许用线程参数调节等手段刷分。
