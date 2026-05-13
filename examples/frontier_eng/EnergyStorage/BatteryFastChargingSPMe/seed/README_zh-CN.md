# BatteryFastChargingSPMe

这是该任务的导航文档。

## 目标

基于一个受 `SPMe-T-Aging` 启发的降阶电化学-热-老化模型，为锂离子电池设计分段快充策略。

相比 `BatteryFastChargingProfile`，这个任务额外包含：

- 正负极分开的固相表面动力学，
- 电解液极化动态，
- 带 Butler-Volmer 风格的动力学过电势代理，
- 热耦合，
- 具有更明确物理含义的析锂裕度与 SEI 老化代理。

## 文件结构

- `Task.md`：英文任务说明与评分规则。
- `Task_zh-CN.md`：中文任务说明。
- `references/README.md`：英文建模说明。
- `references/README_zh-CN.md`：中文建模说明。
- `references/battery_config.json`：电池、模型和评分参数配置。
- `scripts/init.py`：最小可运行初始程序。
- `baseline/solution.py`：基线充电策略。
- `verification/evaluator.py`：评测器入口。
- `verification/requirements.txt`：本地运行依赖。
- `verification/docker/Dockerfile`：可选 Docker 环境。
- `frontier_eval/`：`python -m frontier_eval` 所需元数据。

## 环境准备

在仓库根目录执行：

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/EnergyStorage/BatteryFastChargingSPMe/verification/requirements.txt
```

## 快速运行

在仓库根目录执行：

```bash
python benchmarks/EnergyStorage/BatteryFastChargingSPMe/verification/evaluator.py \
  benchmarks/EnergyStorage/BatteryFastChargingSPMe/scripts/init.py
```

或在任务目录执行：

```bash
cd benchmarks/EnergyStorage/BatteryFastChargingSPMe
python verification/evaluator.py scripts/init.py
```

如果要显式指定参数文件：

```bash
python verification/evaluator.py scripts/init.py --config references/battery_config.json
```

## frontier_eval 任务名

该任务通过 unified task 接入框架，可直接运行：

```bash
python -m frontier_eval task=battery_fast_charging_spme algorithm.iterations=0
```
