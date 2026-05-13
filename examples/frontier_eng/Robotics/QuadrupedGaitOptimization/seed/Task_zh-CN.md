# 四足机器人步态优化（Quadruped Gait Optimization）

## 1. 背景

宇树 A1/Go2、Boston Dynamics Spot 等四足机器人正越来越多地应用于巡检、搜救和物流场景。与轮式机器人不同，其运动性能高度依赖**步态参数**：落脚时序、几何序列和抬腿幅度。参数选择不当会导致运动缓慢、能耗高或失稳；最优参数则能媲美动物的灵活运动。

本任务要求 Agent 在满足运动学可行性、动力学稳定性和地面摩擦约束的前提下，找到使四足机器人在平坦地面上**平均前向速度最大**的步态参数集合。

## 2. 机器人规格

机器人以**宇树 A1**四足机器人为原型建模。

### 2.1 机体参数

| 参数               | 值        |
|--------------------|----------|
| 机体质量           | 13.0 kg  |
| 含腿总质量         | 14.4 kg  |
| 机体长度           | 0.366 m  |
| 机体宽度           | 0.094 m  |
| 标称机体高度       | 0.27 m   |
| 最大腿长           | 0.35 m   |
| 最小腿长           | 0.10 m   |
| 地面摩擦系数 μ     | 0.6      |

### 2.2 髋关节位置（机体坐标系，x 朝前，y 朝左，z 朝上）

| 腿  | x (m)   | y (m)   |
|-----|---------|---------|
| FL  | +0.183  | +0.047  |
| FR  | +0.183  | −0.047  |
| RL  | −0.183  | +0.047  |
| RR  | −0.183  | −0.047  |

## 3. 步态模型

步态是周期性落脚模式。步态周期时长 `T_cycle = 1 / step_frequency` 秒，由以下两相组成：

- **支撑相**（时长 `duty_factor × T_cycle`）：脚与地面接触。
- **摆动相**（时长 `(1 − duty_factor) × T_cycle`）：脚在空中，沿正弦弧线运动。

每条腿有独立的**相位偏移** `φ ∈ [0, 1)`（相对于 FL 腿）。当 `(t / T_cycle + φ) mod 1 < duty_factor` 时，该腿处于支撑相。

### 3.1 摆动相足端轨迹

摆动相归一化时间 `s ∈ [0, 1]`：

```
foot_x(s) = hip_x + step_length × (s − 0.5)          # 前向扫掠
foot_z(s) = −body_height + step_height × sin(π × s)   # 正弦抬腿
```

支撑相期间，脚保持固定，机体从其上方向前移动。

## 4. 决策变量

提交包含 **8 个实数参数**的 JSON 对象：

| 参数         | 符号              | 取值范围     | 单位 |
|------------|-------------------|------------|------|
| 步频         | `step_frequency`  | [0.5, 4.0] | Hz   |
| 占空比       | `duty_factor`     | [0.30, 0.85] | —  |
| 步长         | `step_length`     | [0.04, 0.40] | m  |
| 抬腿高度     | `step_height`     | [0.02, 0.15] | m  |
| FR 相位偏移  | `phase_FR`        | [0.0, 1.0) | —   |
| RL 相位偏移  | `phase_RL`        | [0.0, 1.0) | —   |
| RR 相位偏移  | `phase_RR`        | [0.0, 1.0) | —   |
| 侧向距离     | `lateral_distance`| [0.08, 0.20] | m |

> **注意**：FL 腿为相位基准（φ_FL = 0），三个 `phase_*` 分别对应 FR、RL、RR 腿。  
> `lateral_distance` 为足端接触点到机体中心线的横向距离。

## 5. 约束条件

### 5.1 运动学可行性（硬约束）

在步态周期任意时刻，所需腿长须满足：

```
L_min ≤ L_leg(t) ≤ L_max
```

其中 `L_leg` 为髋关节到足端的欧氏距离。违反 → 得分 = 0。

### 5.2 无腾空相（硬约束）

任意时刻至少有一条腿处于支撑相（每周期采样 200 点）。全腾空导致坠落，得分 = 0。

### 5.3 动力学稳定性——ZMP 准则（软约束）

**零力矩点（ZMP）**须始终位于当前支撑多边形（支撑脚位置的凸包）内。稳定裕度 `m` 为质心投影到支撑多边形边界的有符号距离（内部为正，外部为负）。

稳定性因子：

```
stability_factor = clip(1 + 5 × m_min, 0, 1)
```

其中 `m_min` 为一个周期内的最小裕度。

### 5.4 摩擦约束（软约束）

地面反力的水平/垂直比率不得超过摩擦系数 `μ = 0.6`：

```
F_vertical   = (body_mass × g) / n_stance_legs
F_horizontal = body_mass × a_horizontal / n_stance_legs
friction_ratio = F_horizontal / F_vertical
```

摩擦因子：

```
friction_factor = clip(1 − max(friction_ratio − μ, 0) × 2, 0.1, 1)
```

## 6. 评分

**第一步** — 名义速度（来自步态运动学）：

```
v_nominal = step_length × step_frequency   [m/s]
```

**第二步** — 乘以软约束因子：

```
score = v_nominal × stability_factor × friction_factor
```

**第三步** — 硬约束检查：若任一硬约束违反，`score = 0`。

**得分：`score`（m/s），越高越好。**

### 参考值

| 步态类型 | 典型相位偏移 (FR, RL, RR) | 典型速度   |
|--------|--------------------------|----------|
| 步行（Walk）  | (0.25, 0.75, 0.50) | 0.3–0.5 m/s |
| 对角步（Trot）| (0.50, 0.50, 0.00) | 0.5–1.0 m/s |
| 跳跃（Bound） | (0.00, 0.50, 0.50) | 0.8–1.5 m/s |
| 侧对步（Pace）| (0.50, 0.00, 0.50) | 0.5–0.9 m/s |

## 7. 输入 / 输出

### 7.1 输入

无需外部数据文件，所有参数均包含在本文档及 `references/gait_config.json` 中。

### 7.2 输出

生成 `submission.json`：

```json
{
  "step_frequency":    1.6,
  "duty_factor":       0.6,
  "step_length":       0.15,
  "step_height":       0.06,
  "phase_FR":          0.5,
  "phase_RL":          0.5,
  "phase_RR":          0.0,
  "lateral_distance":  0.13
}
```

所有参数须在第 4 节指定的范围内。

## 8. 评测流程

`verification/evaluator.py` 执行：

1. 读取 `submission.json` 并验证 8 个参数的范围。
2. 以 200 个时间点均匀采样步态周期。
3. 在每个采样点检查运动学可行性（腿长范围）。
4. 检查是否存在腾空相。
5. 在每个采样点计算 ZMP 稳定裕度。
6. 估计地面摩擦力比率。
7. 计算并输出最终得分。

## 9. 基线方案

`baseline/solution.py` 实现标准**对角步（Trot）步态**（FL+RR 同步，FR+RL 同步，偏移 0.5）。这是四足运动的常见起点，但仍有较大速度提升空间。

## 10. 参考资料

- `references/gait_config.json` — 全部数值常数
- Raibert, M. H. (1986). *Legged Robots That Balance*. MIT Press.
- 宇树 A1 规格：https://www.unitree.com/a1/
- Vukobratović & Borovac (2004). Zero-moment point — thirty five years of its life. *IJHR*.
