# 机械臂节拍时间优化

使七自由度 KUKA LBR iiwa 机械臂从起始构型运动到目标构型的轨迹时间最短，同时保证全程无碰撞。

## 文件结构

```
RobotArmCycleTimeOptimization/
├── Task.md                    # 完整任务说明
├── Task_zh-CN.md              # 任务说明（中文）
├── references/
│   └── robot_config.json      # DH 参数、关节限位、障碍物定义
├── verification/
│   ├── evaluator.py           # 评分脚本
│   ├── requirements.txt       # Python 依赖
│   └── docker/
│       └── Dockerfile
└── baseline/
    └── solution.py            # 参考方案（线性插值 + 避障中间点）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线方案

```bash
python baseline/solution.py
# 输出: submission.json
```

### 3. 评测

```bash
python verification/evaluator.py --submission submission.json
# 输出: {"score": <T 秒>, "feasible": true/false}
```

### 4. Docker 评测

```bash
cd verification
docker build -t arm-eval -f docker/Dockerfile .
docker run --rm -v $(pwd)/../submission.json:/workspace/submission.json arm-eval
```

## 提交格式

`submission.json`：

```json
{
  "waypoints": [
    [0.0,  0.5,  0.0, -1.5, 0.0, 1.0, 0.0],
    [0.3,  0.1,  0.4, -1.1, 0.2, 0.9, 0.5],
    [1.2, -0.3,  0.8, -0.8, 0.5, 0.8, 1.0]
  ],
  "timestamps": [0.0, 1.2, 2.5]
}
```

## 评分

| 结果 | 得分 |
|------|------|
| 可行轨迹 | `T` 秒（越低越好） |
| 任一约束违反 | `+inf`（不可行） |

## 任务摘要

- **机器人**：KUKA LBR iiwa 14 R820（7 自由度）
- **起始构型**：`[0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0]` rad
- **目标构型**：`[1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0]` rad
- **障碍物**：AABB，中心 `[0.45, -0.35, 0.65]`，半尺寸 `[0.08, 0.20, 0.08]` m
- **优化目标**：最小化总时间 `T`

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization`

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=robot_arm_cycle_time`。
