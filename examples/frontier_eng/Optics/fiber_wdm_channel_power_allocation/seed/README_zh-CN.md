# 光通信 F1：WDM 信道与功率分配

## 背景

在 WDM 系统中，多个固定栅格信道共享同一链路。调度函数需要决定：

1. 每个用户分配到哪个信道
2. 各信道发射功率如何分配

这会直接影响 BER/SNR、可达速率和频谱利用率。

## Agent 可编辑目标

- `baseline/init.py`
- 函数：`allocate_wdm(...)`

建议只进化这个策略函数。

## 目录说明

- `baseline/init.py`: 基础实现（顺序分配 + 等功率）
- `verification/oracle.py`: 更优参考策略（不可编辑，支持 `auto/hybrid_scipy/heuristic`）
- `verification/run_validation.py`: valid 检查、打分、对比、可视化
- `Task.md`: 任务完整定义

## 环境依赖

一条命令安装（推荐）：

```bash
python -m pip install -r benchmarks/Optics/requirements.txt
```

必需依赖（baseline + verification）：

- 推荐解释器：`python`
- `numpy`
- `matplotlib`
- `optic`（本仓库内 OptiCommPy 包，verification 通过它调用 `theoryBER`）

可选依赖（更强 oracle 模式）：

- `scipy`（使用 `--oracle-mode hybrid_scipy` 时需要；`auto` 模式不可用时会回退）

## 运行方法

```bash
python \
  benchmarks/Optics/fiber_wdm_channel_power_allocation/verification/run_validation.py
```

输出文件：

- `verification/outputs/summary.json`
- `verification/outputs/task1_verification.png`
