# 光通信 F2：MCS + 功率联合调度

## 背景

调度器需要为每个用户联合选择：

1. 调制阶数（MCS，如 4/16/64-QAM）
2. 发射功率

MCS 越高吞吐越高，但需要更好的 SNR，误码风险也更高。

## Agent 可编辑目标

- `baseline/init.py`
- 函数：`select_mcs_power(...)`

## 目录结构

- `baseline/init.py`: 阈值规则基础实现
- `verification/oracle.py`: 更优参考策略（`auto/exact/heuristic`，CP-SAT + DP回退）
- `verification/run_validation.py`: valid 检查、打分与图表
- `Task.md`: 完整任务说明

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

- `ortools`（使用 `--oracle-mode exact` 时需要；`auto` 模式不可用时会回退到 DP）

## 运行

```bash
python \
  benchmarks/Optics/fiber_mcs_power_scheduling/verification/run_validation.py
```

输出：

- `verification/outputs/summary.json`
- `verification/outputs/task2_verification.png`
