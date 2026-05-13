# BatteryFastChargingProfile

这是该任务的导航文档。

## 目标

为一颗锂离子电池设计从 `10%` SOC 充到 `80%` SOC 的多阶段恒流快充策略。

优化目标是在尽可能缩短充电时间的同时，控制：

- 端电压不过限，
- 电芯温度不过热，
- 析锂风险和寿命损失尽量低。

## 文件结构

- `Task.md`：英文任务说明与评分规则。
- `Task_zh-CN.md`：中文任务说明。
- `references/README.md`：英文工业背景与建模说明。
- `references/README_zh-CN.md`：中文工业背景与建模说明。
- `references/battery_config.json`：电池、热环境和评分参数配置。
- `scripts/init.py`：最小可运行初始程序。
- `baseline/solution.py`：简单基线策略。
- `verification/evaluator.py`：评测器入口。
- `verification/requirements.txt`：本地运行依赖。
- `verification/docker/Dockerfile`：可选 Docker 评测环境。
- `frontier_eval/`：用于 `python -m frontier_eval` 的统一任务元数据。

## 环境准备

在仓库根目录执行：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/EnergyStorage/BatteryFastChargingProfile/verification/requirements.txt
```

## 快速运行

在仓库根目录执行：

```bash
python benchmarks/EnergyStorage/BatteryFastChargingProfile/verification/evaluator.py \
  benchmarks/EnergyStorage/BatteryFastChargingProfile/scripts/init.py
```

或在任务目录执行：

```bash
cd benchmarks/EnergyStorage/BatteryFastChargingProfile
python verification/evaluator.py scripts/init.py
```

`scripts/init.py` 应当可以直接运行，并输出一个可行快充策略，使 `combined_score` 非零且 `valid=1.0`。

如果想测试不同的电池参数，可执行：

```bash
python verification/evaluator.py scripts/init.py --config references/battery_config.json
```

## frontier_eval 任务名

该任务通过 unified task 接入框架，可直接运行：

```bash
python -m frontier_eval task=battery_fast_charging_profile algorithm.iterations=0
```
