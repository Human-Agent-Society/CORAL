# 自适应光学 A1：受约束 DM 控制

该任务聚焦于形变镜（DM）在电压约束下的单步控制优化。

## 任务意义

AO 中常见控制是 `u = R @ s`。
实际硬件要求电压有上下限，所以通常会做 `clip`。
但“先无约束求解，再强行 clip”一般不是最优解。

本任务要求 agent 在严格电压约束下提升补偿质量。

## 目录结构

```text
task1_constrained_dm_control/
  baseline/
    init.py                        # agent 修改目标
  verification/
    evaluate.py                    # valid 校验 + baseline/reference 对比
    reference_controller.py        # 更优参考实现
    outputs/                       # 运行后生成
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## 环境依赖

`pip install -r benchmarks/Optics/requirements.txt`

## 运行方式

```bash
cd benchmarks/Optics/adaptive_constrained_dm_control
python verification/evaluate.py
```

指定候选实现：

```bash
python verification/evaluate.py \
  --candidate /path/to/your/solution.py
```

## 输出文件

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`

`metrics.json` 会在相同随机种子和场景下对比候选 baseline 与 reference。
