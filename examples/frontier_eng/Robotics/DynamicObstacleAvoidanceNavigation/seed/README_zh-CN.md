# 动态障碍避让导航（Dynamic Obstacle Avoidance Navigation）

在二维环境中控制差分轮机器人从起点到终点，环境同时包含静态障碍与动态障碍。

## 文件结构

```
DynamicObstacleAvoidanceNavigation/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── references/
│   └── scenarios.json
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
└── baseline/
    ├── solution.py
    └── result_log.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 生成基线提交

```bash
python baseline/solution.py
# 生成 submission.json
```

### 3. 运行评测

```bash
python verification/evaluator.py --submission submission.json
# 输出: {"score": <float|null>, "feasible": <bool>, "details": {...}}
```

## 提交格式

`submission.json`：

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.2, 0.4],
      "controls": [[0.0, 0.0], [0.7, 0.4], [0.8, 0.2]]
    }
  ]
}
```

## 评分规则

- 固定 3 个场景必须全部成功才算可行。
- 得分为 3 个场景到达时间平均值（越小越好）。
- 任一场景发生碰撞、越界、限值违规或超时即失败。
- 若任一场景失败，则最终 `feasible=false` 且 `score=null`。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation`

```bash
python -m frontier_eval task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=dynamic_obstacle_navigation`。
