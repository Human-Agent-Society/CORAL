# 相位 DOE P4 说明：大规模加权焦点阵列

## 背景
这个任务是“多目标能量分配”问题：
- 决策变量：相位矩阵 `(N, N)`
- 前向模型：Fourier 传播
- 目标：在 8x8 大规模焦点阵列上满足加权配光

相比 Task01，这题目标数量更多、分布更广。

## 你要做什么
改进 baseline 相位生成逻辑，提高大规模焦点阵列质量。

主要修改函数：
- `solve_baseline(problem)`

## 可修改边界
- 可修改：`baseline/init.py`
- 只读：`verification/validate.py`

评测依赖接口：
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### 输入 `problem`
- `x`, `y`：像素坐标
- `aperture_amp`：孔径掩膜，形状 `(N, N)`
- `spots`：64 个目标焦点坐标
- `weights`：归一化目标权重
- `cfg`：SLM 与网格参数

### 输出
- `phase`：形状 `(N, N)` 的相位图（弧度）

## Baseline 当前实现
baseline 使用非迭代的加权平面波叠加，然后直接取相位。

## Oracle 当前实现
oracle 使用 `slmsuite` 的迭代 WGS：
- `Hologram.optimize(method="WGS-Kim")`

## 指标与分数（越高越好）
原始指标：
- `ratio_mae`
- `cv_spots`
- `efficiency`

分数公式：
- `ratio_score = clip(1 - ratio_mae / 0.03, 0, 1)`
- `uniform_score = clip(1 - cv_spots / 1.40, 0, 1)`
- `efficiency_score = clip((efficiency - 0.40) / (0.90 - 0.40), 0, 1)`
- `score_pct = 100 * (0.45*ratio_score + 0.35*uniform_score + 0.20*efficiency_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
- `score_pct >= 20`
- `ratio_mae <= 0.03`
- `cv_spots <= 1.40`
- `efficiency >= 0.50`

## 可行优化方向
- 迭代权重修正（替代一次性相位）
- 局部相位细化或分块更新
- 动态平衡配光误差与效率

