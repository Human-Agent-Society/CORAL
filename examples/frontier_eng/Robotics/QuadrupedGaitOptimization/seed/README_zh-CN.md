# 四足机器人步态优化

通过优化 8 个步态参数，最大化宇树 A1 仿真四足机器人的前向运动速度。

## 文件结构

```
QuadrupedGaitOptimization/
├── Task.md                    # 完整任务说明
├── Task_zh-CN.md              # 任务说明（中文）
├── references/
│   └── gait_config.json       # 机器人参数与评测常数
├── verification/
│   ├── evaluator.py           # 评分脚本（纯 Python + NumPy）
│   ├── requirements.txt
│   └── docker/
│       └── Dockerfile
└── baseline/
    └── solution.py            # 对角步（Trot）基线方案
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线（对角步步态）

```bash
python baseline/solution.py
# 输出: submission.json
```

### 3. 评测

```bash
python verification/evaluator.py --submission submission.json
# 输出: {"score": <速度 m/s>, "feasible": true}
```

### 4. Docker 评测

```bash
cd verification
docker build -t quad-eval -f docker/Dockerfile .
docker run --rm -v $(pwd)/../submission.json:/workspace/submission.json quad-eval
```

## 提交格式

`submission.json`：

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

## 评分

| 结果 | 得分 |
|------|------|
| 有效步态 | `v` m/s（越高越好） |
| 硬约束违反 | `0.0` |

## 任务摘要

- **机器人**：宇树 A1 仿真四足机器人（机体 13 kg，4 条腿）
- **决策变量**：8 个步态参数（频率、占空比、步长/抬腿高度、3 个相位偏移、侧向距离）
- **硬约束**：运动学可行性（腿长限制）、无腾空相
- **软约束**：ZMP 稳定裕度、地面摩擦力限制
- **优化目标**：最大化前向速度（m/s）
- **基线**（对角步）：约 0.24 m/s

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Robotics/QuadrupedGaitOptimization`

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/QuadrupedGaitOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=quadruped_gait`。
