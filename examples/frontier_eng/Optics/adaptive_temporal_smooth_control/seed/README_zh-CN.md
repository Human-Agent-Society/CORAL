# 自适应光学 A2：时间平滑控制

该任务聚焦于 **时序 AO 控制** 中“补偿质量 + 命令平滑”折中优化。

## 任务意义

真实系统中命令抖动会带来：
- 执行器磨损，
- 镜面振动风险，
- 闭环鲁棒性下降。

逐帧独立控制可能瞬时误差低，但时间轨迹不平滑。
本任务强调工程可用的综合目标。

## 目录结构

```text
task2_temporal_smooth_control/
  baseline/
    init.py
  verification/
    evaluate.py
    reference_controller.py
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## 环境依赖

- Python：`3.10+`（已验证解释器：`python`）
- Baseline 候选实现运行依赖：`numpy`
- Verification 评测依赖：`numpy`、`matplotlib`、仓库内本地 `aotools` 包
- 任务特定 oracle 依赖：无（reference 为解析控制器，不依赖额外第三方求解器）
- 建议在仓库根目录一次安装：`python -m pip install -r benchmarks/Optics/requirements.txt`

## 运行方式

```bash
cd benchmarks/Optics/adaptive_temporal_smooth_control
python verification/evaluate.py
```

## 输出

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`
