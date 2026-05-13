# 动态障碍避让导航（Dynamic Obstacle Avoidance Navigation）

## 1. 背景

仓储、工厂、医院中的移动机器人需要在动态环境中快速到达目标，同时保证不碰撞。

## 2. 任务定义

在每个固定场景中，控制差分轮机器人从起点到目标点，并满足运动学约束。

### 2.1 机器人运动模型

仿真步长固定为 `dt = 0.05 s`：

```
x_{k+1} = x_k + v_k * cos(theta_k) * dt
y_{k+1} = y_k + v_k * sin(theta_k) * dt
theta_{k+1} = theta_k + omega_k * dt
```

### 2.2 输入

`references/scenarios.json` 固定提供 3 个场景，每个场景包含：

- 地图边界
- 静态障碍（圆形/矩形）
- 动态障碍（分段线性轨迹）
- 机器人参数（`radius`, `v_max`, `omega_max`, `a_max`）
- 起点状态与目标点
- 最大时间 `T_max`

## 3. 提交格式

提交 `submission.json`：

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.2, ...],
      "controls": [[v0, w0], [v1, w1], ...]
    }
  ]
}
```

要求：

- `timestamps` 严格递增，且起点为 `0.0`
- `len(controls) == len(timestamps)`
- 控制量满足速度/角速度上限
- 相邻控制满足加速度上限

## 4. 约束

任一场景出现以下情况即失败：

1. 与静态或动态障碍碰撞
2. 机器人越界
3. 控制量违规
4. `T_max` 内未到达目标

到达判定：`distance(robot, goal) <= goal_tolerance`。

## 5. 优化目标与评分

- 目标：最小化到达时间。
- 只有 3/3 场景全部成功才算可行。
- 可行时：得分为 3 个场景到达时间平均值（越小越好）。
- 不可行时：`score = null`, `feasible = false`。

## 6. 评测输出

`verification/evaluator.py` 输出 JSON：

```json
{
  "score": 8.4,
  "feasible": true,
  "details": {
    "scene_1": {"success": true, "time": 7.9},
    "scene_2": {"success": true, "time": 8.6},
    "scene_3": {"success": true, "time": 8.7}
  }
}
```
