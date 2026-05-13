# HighReliableSimulation

本任务导航文档。

## 目标

实现 `MySampler`（继承 `SamplerBase`），并提供 `simulate_variance_controlled(...)` 以兼容本地调用。官方评分会使用 benchmark 自己的方差控制循环和你的 sampler，在固定评测配置下估计 AWGN 信道中 Hamming(127,120) 的 BER。

## 文件

- `Task.md`：任务协议与评分规则（英文）。
- `Task_zh-CN.md`：任务协议中文版。
- `scripts/init.py`：最小可运行示例。
- `baseline/solution.py`：基线实现。
- `runtime/`：任务运行组件。
- `verification/evaluator.py`：评测入口。
- `verification/requirements.txt`：本地运行评测器的最小依赖。

## 环境配置

在仓库根目录执行：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/WirelessChannelSimulation/HighReliableSimulation/verification/requirements.txt
```

## 快速运行

在仓库根目录执行：

```bash
python benchmarks/WirelessChannelSimulation/HighReliableSimulation/verification/evaluator.py benchmarks/WirelessChannelSimulation/HighReliableSimulation/scripts/init.py
```

或在任务目录执行：

```bash
cd benchmarks/WirelessChannelSimulation/HighReliableSimulation && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` 是可运行初始程序；在正常环境下应出现非零 `runtime_s`。它只是兼容性的 starter，不保证在冻结的 `target_std` 门槛下得到 `valid=1.0`。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=WirelessChannelSimulation/HighReliableSimulation`

示例：

```bash
python -m frontier_eval task=unified task.benchmark=WirelessChannelSimulation/HighReliableSimulation algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=high_reliable_simulation`。
