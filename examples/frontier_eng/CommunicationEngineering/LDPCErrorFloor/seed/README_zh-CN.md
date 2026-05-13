# LDPC 错误地板估计

本任务的导航文档。

## 目标

使用重要性采样估计LDPC（低密度奇偶校验）码的错误地板。LDPC码在极低误码率区域会出现"错误地板"现象，这是由码图中的特殊结构（如Trapping Sets）导致的。直接的蒙特卡洛仿真几乎不可能观察到这些罕见事件。

## 文件

- `Task.md`: 任务契约和评分规则（英文）。
- `Task_zh-CN.md`: 任务契约的中文版本。
- `scripts/init.py`: 最小可运行启动程序。
- `baseline/solution.py`: 基线实现。
- `runtime/`: 任务运行时组件（LDPC码、译码器、采样器基类）。
- `verification/evaluator.py`: 评估器入口。
- `verification/requirements.txt`: 本地评估器运行所需的最小依赖项。

## 环境

从仓库根目录：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/LDPCErrorFloor/verification/requirements.txt
```

## 快速运行

从仓库根目录运行：

```bash
python benchmarks/CommunicationEngineering/LDPCErrorFloor/verification/evaluator.py benchmarks/CommunicationEngineering/LDPCErrorFloor/scripts/init.py
```

或从任务目录运行：

```bash
cd benchmarks/CommunicationEngineering/LDPCErrorFloor && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` 应该是可运行的，在正常环境下应产生非零的 `error_rate_log` 和 `valid=1.0`。

## frontier_eval 任务名称

此任务的注册 `task_name`：

```text
ldpc_error_floor
```

该任务运行耗时较长需要增加运行时间上限
示例：

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/LDPCErrorFloor algorithm.iterations=0 algorithm.oe.evaluator.timeout=60
```


