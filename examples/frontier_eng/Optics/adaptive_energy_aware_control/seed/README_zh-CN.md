# 自适应光学 A3：能耗感知控制

该任务引入“补偿质量 vs 命令能耗”的工程折中。

## 任务意义

实际 AO 硬件中，命令幅值与以下问题直接相关：
- 功耗/热负载，
- 长期可靠性，
- 驱动电路裕量。

仅优化残差通常会得到高能耗、稠密命令。
本任务要求提升综合效率。

## 目录结构

```text
task3_energy_aware_control/
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
- 任务特定 oracle 依赖：`scikit-learn`（`verification/reference_controller.py` 使用 `sklearn.linear_model.Lasso`）
- 建议在仓库根目录一次安装：`python -m pip install -r benchmarks/Optics/requirements.txt`

## 运行方式

```bash
cd benchmarks/Optics/adaptive_energy_aware_control
python verification/evaluate.py
```

## 输出

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`