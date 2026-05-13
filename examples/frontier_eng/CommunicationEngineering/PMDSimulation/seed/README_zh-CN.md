# PMD 仿真

本任务的导航文档。

## 目标

使用重要性采样在光纤系统中仿真偏振模色散（PMD）。光纤系统通常要求极低的中断概率（例如 $10^{-12}$），而 PMD 是一种随机物理现象。这被认为是重要性采样在工程中最成功的应用之一。

## 文件

- `Task.md`: 任务契约和评分规则（英文）。
- `Task_zh-CN.md`: 任务契约的中文版本。
- `scripts/init.py`: 最小可运行启动程序。
- `baseline/solution.py`: 基线实现。
- `runtime/`: 任务运行时组件（PMD 模型、光纤仿真）。
- `verification/evaluator.py`: 评估器入口。
- `verification/requirements.txt`: 本地评估器运行所需的最小依赖项。

## 环境

从仓库根目录：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/PMDSimulation/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/CommunicationEngineering/PMDSimulation/verification/evaluator.py benchmarks/CommunicationEngineering/PMDSimulation/scripts/init.py
```

或从任务目录运行：

```bash
cd benchmarks/CommunicationEngineering/PMDSimulation && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` 应该是可运行的，在正常环境下应产生非零的 `outage_prob_log` 和 `valid=1.0`。

## frontier_eval 任务名称

此任务使用统一任务框架。运行：

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/PMDSimulation algorithm.iterations=0
```
