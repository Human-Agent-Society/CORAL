# 光通信 F4：保护带约束频谱打包

## 背景

不同用户需要不同宽度的频谱槽位。调度器要在有限槽位中完成打包，并在相邻业务间保留保护带。

这会影响：

- 请求接纳率
- 频谱利用率
- 碎片化程度
- 邻道干扰风险（通过 BER 代理项体现）

## Agent 可编辑目标

- `baseline/init.py`
- 函数：`pack_spectrum(...)`

## 目录结构

- `baseline/init.py`: First-Fit Decreasing 基础策略
- `verification/oracle.py`: 更优参考（`auto/hybrid/exact_geometry/heuristic`）
- `verification/run_validation.py`: valid 检查、评分、可视化
- `Task.md`: 完整任务定义

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

- `ortools`（使用 `--oracle-mode exact_geometry` 时需要；`auto` 模式不可用时会回退到 heuristic/hybrid）

## 运行

```bash
python \
  benchmarks/Optics/fiber_guardband_spectrum_packing/verification/run_validation.py
```

输出：

- `verification/outputs/summary.json`
- `verification/outputs/task4_verification.png`
