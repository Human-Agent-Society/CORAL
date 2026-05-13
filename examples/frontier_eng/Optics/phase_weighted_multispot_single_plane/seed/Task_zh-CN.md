# 相位 DOE P1 说明：高难度加权多焦点

## 背景
你可以把这个任务理解为一个 **二维数组优化问题**：
- 输入：相位矩阵 `phase[y, x]`
- 前向黑盒：`phase -> 远场强度图`
- 目标：让很多目标焦点按给定比例分配能量

光学上是纯相位 Fourier 全息；算法上是非凸优化问题。

## 你要做什么
改进 `baseline/init.py`，让生成的相位图在“稠密、多目标、非均匀配光”场景下取得更高分。

建议主要修改：
- `solve_baseline(problem)`

可以在同文件增加辅助函数，但不要改公共接口。

## 可修改边界
- 可修改：`baseline/init.py`
- 只读（评测逻辑）：`verification/validate.py`

评测依赖接口：
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### `solve_baseline(problem)` 的输入
`problem` 由 `build_problem` 生成，关键字段：
- `x`, `y`：像素坐标（一维数组）
- `aperture_amp`：孔径掩膜，形状 `(N, N)`
- `spots`：目标焦点坐标，形状 `(K, 2)`
- `weights`：归一化目标权重，形状 `(K,)`
- `cfg`：配置参数（像素数、网格规模等）

### `solve_baseline(problem)` 的输出
- `phase`：形状 `(N, N)` 的浮点相位矩阵（单位弧度）

## 核心可改函数
核心修改点：
- `solve_baseline(problem)`

评测流程：
1. 调用你的 `solve_baseline`
2. 调用 `forward_intensity(problem, phase)`
3. 计算指标和分数
4. 与 oracle 对比

## Baseline 当前实现
当前 baseline 是有意简化的：
1. 每个目标焦点构造一个复平面波项
2. 按权重做相干叠加
3. 取叠加结果的相位作为输出相位图

优点是快；缺点是不迭代，面对稠密非均匀目标容易失配。

## Oracle 当前实现
评测内置 oracle 使用 `slmsuite` 的加权 GS：
- `Hologram.optimize(method="WGS-Kim")`
- 通过迭代更新来逼近目标配光

因此 oracle 是强迭代方法，baseline 是弱非迭代方法。

## 指标与分数（越高越好）
评测计算：
- `ratio_mae`：实际焦点比例与目标比例的平均绝对误差（越小越好）
- `cv_spots`：焦点能量变异系数（越小越好）
- `efficiency`：目标窗口总能量占比（越大越好）
- `min_peak_ratio`：最弱峰 / 最强峰（越大越好）

分数公式：
- `ratio_score = clip(1 - ratio_mae / 0.07, 0, 1)`
- `uniform_score = 1 / (1 + (cv_spots / 0.85)^2)`
- `efficiency_score = clip((efficiency - 0.15) / (0.80 - 0.15), 0, 1)`
- `peak_score = clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0, 1)`
- `score = 0.25*ratio_score + 0.45*uniform_score + 0.20*efficiency_score + 0.10*peak_score`
- `score_pct = 100 * score`（兼容字段）

范围：`0 ~ 1`，越高越好。

## valid 判定
baseline 同时满足以下条件才算 valid：
- `score >= 0.20`
- `efficiency >= 0.45`
- `min_peak_ratio > 0`

## 可行优化方向
常见有效改法：
- GS/WGS 类迭代相位检索
- 按焦点误差做反馈修正
- 加阻尼或正则提高稳定性
- 更好的初始化（优于直接叠加）
