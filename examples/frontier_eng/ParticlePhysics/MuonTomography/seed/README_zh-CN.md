# 粒子物理：缪子成像探测器阵列布局优化

[English](./README.md) | 简体中文

## 1. 任务简介

本任务（Muon Tomography Optimization）是 `Frontier-Eng` 基准测试在**粒子物理与核技术工程**领域的核心优化问题。

缪子成像技术利用宇宙射线缪子的透射衰减特性来探测大型结构（如金字塔、火山、核反应堆）的内部结构。本任务要求 AI Agent 在考虑真实的物理约束（如缪子通量随天顶角的 $\cos^2(\theta_z)$ 衰减）和严格的经济约束（探测器造价、地下挖掘成本）的前提下，寻找一组最佳的探测器空间布局方案。

> **核心挑战**：Agent 不能简单地将探测器堆砌在距离目标最近的地方，而必须通过精确的空间几何计算，在“接收最大有效信号”和“最小化工程成本”之间找到最优的帕累托解。

详细的物理数学模型、目标函数以及输入输出格式，请参阅给 Agent 阅读的专用说明文档：[Task_zh-CN.md](./Task_zh-CN.md)。

## 2. 本地运行方式

准备好 `frontier-eval-driver` 环境后，可以直接在任务目录下运行：

```bash
cd benchmarks/ParticlePhysics/MuonTomography
../../../.venvs/frontier-eval-driver/bin/python baseline/solution.py
../../../.venvs/frontier-eval-driver/bin/python verification/evaluator.py solution.json
```

当前 `verification/requirements.txt` 只要求 `numpy>=1.24.0`。

我在当前仓库里用上面的命令实际验证过，baseline 结果如下：

```json
{"score": 199.32012533144325, "status": "success", "metrics": {"total_signal": 309.32012533144325, "total_cost": 110.0, "valid_detectors": 4}}
```

## 3. 通过 `frontier_eval` 运行

该任务现在通过 unified benchmark 入口运行：
`task=unified task.benchmark=ParticlePhysics/MuonTomography`。

在仓库根目录下，可以先用下面的命令做标准兼容性验证：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=ParticlePhysics/MuonTomography algorithm=openevolve algorithm.iterations=0
```

按 [frontier_eval/README_zh-CN.md](../../../frontier_eval/README_zh-CN.md) 完成框架级环境和 `.env` 配置后，就可以把 `algorithm.iterations` 调大，开始真正的搜索，例如：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=ParticlePhysics/MuonTomography algorithm=openevolve algorithm.iterations=10
```

旧别名 `task=muon_tomography` 仍可使用，并会通过配置路由到相同的 unified benchmark。
