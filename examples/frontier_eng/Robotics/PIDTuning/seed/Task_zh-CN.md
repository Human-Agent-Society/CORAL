# PID 调参

## 1. 问题

为二维四旋翼的级联 PID 控制器调节 12 个增益。
控制器必须在多个场景下（不同起点、目标、持续时间和风扰动）保持稳定并跟踪航点目标。

## 2. 动力学与控制器

仿真状态为：

```text
[x, z, theta, x_dot, z_dot, theta_dot]
```

评测器使用：

- 总推力 `T`
- 力矩 `tau`
- 一阶电机滞后
- 线性阻力与角阻力

控制器包含三个 PID 回路：

1. **高度回路**：控制垂直运动
2. **水平回路**：将水平误差转换为期望俯仰角
3. **俯仰回路**：通过力矩跟踪期望俯仰角

微分项采用带滤波器的导数，参数为 `N_z`、`N_x` 和 `N_theta`。

## 3. 决策变量

请提交以下 12 个增益：

- `Kp_z`, `Ki_z`, `Kd_z`, `N_z`
- `Kp_x`, `Ki_x`, `Kd_x`, `N_x`
- `Kp_theta`, `Ki_theta`, `Kd_theta`, `N_theta`

每个值都必须落在 `references/pid_config.json` 中定义的边界范围内。

## 4. 场景

当前配置包含 4 个场景：

1. `vertical_hover`
2. `lateral_move`
3. `combined_wind`
4. `multi_waypoint`

每个场景定义：

- 起始位置
- 航点列表
- rollout 持续时间
- 恒定风扰动

## 5. 提交格式

在工作目录写出 `submission.json`：

```json
{
  "Kp_z": 8.0,
  "Ki_z": 0.5,
  "Kd_z": 4.0,
  "N_z": 20.0,
  "Kp_x": 0.1,
  "Ki_x": 0.01,
  "Kd_x": 0.1,
  "N_x": 10.0,
  "Kp_theta": 10.0,
  "Ki_theta": 0.5,
  "Kd_theta": 3.0,
  "N_theta": 20.0
}
```

所有键都必需且必须为数值。

## 6. 可行性规则

出现以下任一情况，提交不可行：

1. 缺少必需键
2. 增益不是数值
3. 增益超出配置范围
4. 任一场景违反俯仰角限制
5. 任一场景产生非正 ITAE

不可行提交得分为 `0.0`。

## 7. 目标

最小化所有场景随时间累积的跟踪误差。
评测器会为每个场景计算一个 ITAE 风格指标：

```text
ITAE = ∫ t * position_error(t) dt
```

并返回：

```text
score = geometric_mean(1 / ITAE_i)
```

分数越高越好。

## 8. 评测

### 评测已有提交文件

```bash
python verification/evaluator.py --submission submission.json
```

### 运行候选优化脚本并评测其输出

```bash
python verification/evaluator.py scripts/init.py
```

## 9. 参考

- 配置：`references/pid_config.json`
- 基线优化器：`scripts/init.py`
- 评测器：`verification/evaluator.py`
