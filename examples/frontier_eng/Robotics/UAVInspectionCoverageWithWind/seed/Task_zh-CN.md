# UAVInspectionCoverageWithWind

## 1. 背景

无人机在巡检场景中需要在风场扰动下覆盖尽可能多的检查点，同时满足飞行安全与运动约束。

## 2. 动力学模型

仿真固定步长 `dt`（见 `references/scenarios.json`）：

- 状态：`(x, y, z, vx, vy, vz)`
- 控制：`(ax, ay, az)`

更新：

```text
v_{k+1} = v_k + u_k * dt
p_{k+1} = p_k + (v_{k+1} + w(p_k, t_k)) * dt
```

其中 `w(p, t)` 为场景定义的风速扰动。

## 3. 输入场景

固定 3 个场景，每个场景包含：

- 三维边界
- 禁飞区（AABB）
- 动态障碍（分段线性轨迹 + 半径）
- 巡检点集合
- 风场参数
- 无人机限制（`v_max`, `a_max`）
- 起始状态与 `T_max`

## 4. 提交格式

`submission.json`：

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.1, ...],
      "controls": [[ax0, ay0, az0], [ax1, ay1, az1], ...]
    }
  ]
}
```

要求：

- `timestamps` 严格递增，且首元素为 `0.0`
- `controls` 与 `timestamps` 长度一致
- 每个控制量为长度 3 的向量

## 5. 硬约束

任一触发即该场景失败：

1. 越界
2. 进入禁飞区
3. 与动态障碍碰撞
4. 超速（`||v|| > v_max`）
5. 超加速度（`||u|| > a_max`）
6. 提交格式不合法

## 6. 目标与评分

- 覆盖判定：无人机与巡检点距离小于 `coverage_radius` 即覆盖。
- 单场景得分：

```text
scene_score = (coverage_ratio^2) * 1e6 - energy
energy = sum(||u_k||^2 * dt)
```

- 总分：三场景平均。
- 可行性：三场景全部成功才 `feasible=true`；否则 `score=null`。
