# PID 调参

为二维四旋翼在多个飞行场景下调节级联 PID 控制器。
该基准根据给定仿真动力学下的跟踪质量和可行性对候选增益集合进行评分。

## 文件结构

```text
PIDTuning/
├── README.md
├── Task.md
├── references/
│   └── pid_config.json
├── scripts/
│   └── init.py
└── verification/
    ├── evaluator.py
    └── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线优化器

```bash
cd benchmarks/Robotics/PIDTuning
python scripts/init.py
# 输出: submission.json
```

### 3. 评测提交文件

```bash
cd benchmarks/Robotics/PIDTuning
python verification/evaluator.py --submission submission.json
```

### 4. 直接评测候选程序

```bash
cd benchmarks/Robotics/PIDTuning
python verification/evaluator.py scripts/init.py
```

## 提交格式

写出包含 12 个标量增益的 `submission.json`：

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

## 任务摘要

- **系统**: 二维平面四旋翼
- **状态**: `[x, z, theta, x_dot, z_dot, theta_dot]`
- **控制结构**:
  - 高度 PID
  - 水平 PID
  - 俯仰 PID
- **场景**: 定义于 `references/pid_config.json`
- **仿真步长**: `dt = 0.005 s`
- **电机动力学**: 一阶滞后
- **硬可行性条件**:
  - 所有增益必须位于配置范围内
  - 俯仰角必须保持在 `max_pitch_rad` 范围内
  - 每个场景在整个 rollout 期间都必须可行

## 评分

- 每个场景会产生一个类 ITAE 跟踪代价。
- 最终分数是所有场景 `1 / ITAE` 的几何平均值。
- 分数越高越好。
- 若任一场景不可行，或任一 ITAE 非正，最终分数为 `0.0`。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Robotics/PIDTuning`

```bash
python -m frontier_eval \
task=unified task.benchmark=Robotics/PIDTuning \
algorithm.iterations=10
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=pid_tuning`。
