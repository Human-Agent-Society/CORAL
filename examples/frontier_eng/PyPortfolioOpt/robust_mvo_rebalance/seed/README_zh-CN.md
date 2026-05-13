# 任务 01：鲁棒均值方差再平衡

该基准聚焦于一个贴近实盘的单期组合再平衡问题：
在行业暴露、因子暴露、仓位边界、换手率上限等约束下，最大化风险调整收益，同时考虑交易惩罚。

## 这个任务为什么重要

经典 Markowitz 结果通常不能直接下单，工程落地时必须处理：
- 暴露控制（行业约束）；
- 风险风格控制（因子暴露约束）；
- 实施摩擦（换手约束与交易惩罚）；
- 从当前持仓 `w_prev` 平滑过渡到新持仓 `w`。

这个基准把这些约束统一到一个优化问题里。

## 环境配置

请按统一依赖配置安装环境：

```bash
pip install -r benchmarks/PyPortfolioOpt/requirements.txt
```

如果你在当前子目录执行命令，可使用：

```bash
pip install -r ../requirements.txt
```

## 运行方式

在仓库根目录执行：

```bash
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/robust_mvo_rebalance/verification/evaluate.py
```

使用 `frontier_eval` unified 任务运行：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/robust_mvo_rebalance \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

耗时说明：该评测每次会求解多个凸优化问题，明显慢于 smoke 任务。`algorithm.iterations=0` 的单次运行通常约 8-15 秒，总耗时会随迭代次数近似线性增长。

## 目录结构

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── frontier_eval
│   ├── initial_program.txt
│   ├── candidate_destination.txt
│   ├── eval_command.txt
│   ├── agent_files.txt
│   ├── readonly_files.txt
│   ├── artifact_files.txt
│   └── constraints.txt
├── baseline
│   └── init.py
└── verification
    ├── reference.py
    └── evaluate.py
```
