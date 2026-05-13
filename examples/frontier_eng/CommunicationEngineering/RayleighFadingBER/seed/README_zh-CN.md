# 瑞利衰落 BER 分析

本任务的导航文档。

## 目标

使用重要性采样分析瑞利衰落信道下的比特误码率（BER）。在多径衰落信道中，信道增益 $h$ 是随机变量，使平均 BER 计算涉及复杂积分。重要性采样可用于高效仿真深衰落事件。

## 文件

- `Task.md`: 任务契约和评分规则（英文）。
- `Task_zh-CN.md`: 任务契约的中文版本。
- `scripts/init.py`: 最小可运行启动程序。
- `baseline/solution.py`: 基线实现。
- `runtime/`: 任务运行时组件（信道模型、分集合并器）。
- `verification/evaluator.py`: 评估器入口。
- `verification/requirements.txt`: 本地评估器运行所需的最小依赖项。

## 环境

从仓库根目录：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/RayleighFadingBER/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/CommunicationEngineering/RayleighFadingBER/verification/evaluator.py benchmarks/CommunicationEngineering/RayleighFadingBER/scripts/init.py
```

或从任务目录运行：

```bash
cd benchmarks/CommunicationEngineering/RayleighFadingBER && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` 应该是可运行的，在正常环境下应产生非零的 `error_rate_log` 和 `valid=1.0`。

## frontier_eval 任务名称

此任务使用统一任务框架。运行：

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER algorithm.iterations=0
```

或使用短别名（若已注册）：

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER algorithm.iterations=0
```
