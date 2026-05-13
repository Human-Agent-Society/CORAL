# 相位 DOE P2 说明：高难度 Fourier 图案全息

## 背景
这个任务本质是“有约束的图像重建”：
- 决策变量：相位图 `phase[y, x]`
- 前向模型：FFT 传播得到强度图
- 优化目标：既要重建稀疏高对比目标，也要保持暗区足够暗

从算法角度看，它是二维非凸逆问题。

## 你要做什么
改进 `baseline/init.py`，让输出强度图更接近目标结构，并减少暗区泄漏。

建议重点改：
- `solve_baseline(problem, seed=None)`

## 可修改边界
- 可修改：`baseline/init.py`
- 只读：`verification/validate.py`

评测依赖接口：
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict, seed: int | None = None) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### 输入 `problem`
关键字段：
- `x`, `y`：像素坐标
- `aperture_amp`：孔径掩膜，形状 `(N, N)`
- `target_amp`：目标振幅图，形状 `(N, N)`
- `cfg`：参数字典（如 `slm_pixels`, `seed`）

### 输出
- `phase`：形状 `(N, N)` 的相位图（弧度）

## 核心可改函数
主要修改点：
- `solve_baseline(problem, seed=None)`

评测会固定调用该函数，并基于其输出计算指标。

## Baseline 当前实现
当前 baseline 是单次逆变换：
1. 给目标振幅附加随机相位
2. 只做一次逆 FFT
3. 结果相位直接作为全息图

速度快，但在稀疏高对比场景下能力有限。

## Oracle 当前实现
oracle 使用 `slmsuite` 迭代加权 GS：
- `Hologram.optimize(method="WGS-Kim")`
- 通过迭代修正幅度/相位

通常能显著提升重建质量与暗区控制。

## 指标与分数（越高越好）
评测指标：
- `nmse`：预测强度与目标强度的归一化 RMSE
- `energy_in_target`：`target_amp > 0.30` 区域的能量占比
- `dark_suppression`：暗区抑制度，定义为 `1 - leak`，其中 leak 是 `target_amp < 0.03` 区域能量占比

分数公式：
- `pattern_score = clip(1 - nmse / 4.0, 0, 1)`
- `energy_score = clip((energy_in_target - 0.10) / (0.70 - 0.10), 0, 1)`
- `dark_score = clip((dark_suppression - 0.35) / (0.90 - 0.35), 0, 1)`
- `score_pct = 100 * (0.55*pattern_score + 0.30*energy_score + 0.15*dark_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
baseline 满足以下条件则 valid：
- `score_pct >= 20`
- `energy_in_target >= 0.45`
- `dark_suppression >= 0.60`

## 可行优化方向
常见有效策略：
- 迭代相位检索替代单次逆变换
- 针对稀疏目标做区域加权
- 对暗区泄漏引入显式惩罚
- 改进初始化与迭代调度

