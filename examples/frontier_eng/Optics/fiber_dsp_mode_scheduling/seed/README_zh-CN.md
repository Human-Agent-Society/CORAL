# 光通信 F3：DSP 模式调度（EDC vs DBP）

## 背景

接收端 DSP 可选不同补偿模式：

- EDC：时延低，但非线性补偿能力弱
- DBP：时延高，但通常性能更好

在总时延预算下，不能给所有用户都分配 DBP。

## Agent 可编辑目标

- `baseline/init.py`
- 函数：`choose_dsp_mode(...)`

## 目录结构

- `baseline/init.py`: 低SNR优先DBP的基础策略
- `verification/oracle.py`: 更优参考（`auto/exact/heuristic`，CP-SAT + DP回退）
- `verification/run_validation.py`: valid 检查、评分、图表
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

- `ortools`（使用 `--oracle-mode exact` 时需要；`auto` 模式不可用时会回退到 DP）

## 运行

```bash
python \
  benchmarks/Optics/fiber_dsp_mode_scheduling/verification/run_validation.py
```

输出：

- `verification/outputs/summary.json`
- `verification/outputs/task3_verification.png`
