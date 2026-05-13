# UAVInspectionCoverageWithWind（带风场的无人机巡检覆盖）

在存在风扰动与动态障碍的三维场景中，优化无人机控制序列，在满足安全与运动约束的前提下最大化巡检覆盖率。

## 文件结构

```text
UAVInspectionCoverageWithWind/
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

1. 安装依赖：

```bash
pip install -r verification/requirements.txt
```

2. 生成 baseline 提交：

```bash
python baseline/solution.py
```

3. 评测：

```bash
python verification/evaluator.py --submission submission.json
```

## 评分规则

- 主目标：覆盖率 `coverage_ratio` 越高越好。
- 次目标：能耗 `energy` 越低越好（同覆盖率下比较）。
- 单场景分数：`(coverage_ratio^2) * 1e6 - energy`。
- 总分：三场景平均分。
- 任一场景违反硬约束（含动态障碍碰撞）则整体不可行：`feasible=false`, `score=null`。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind`

```bash
python -m frontier_eval task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=uav_inspection_coverage`。
