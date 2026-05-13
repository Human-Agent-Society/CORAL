# 任务 03：带手数约束的离散再平衡（MIP）

该基准描述“可交易化”再平衡：
目标权重必须转换成整数手数，并同时满足预算、换手和交易费约束。

## 这个任务为什么重要

优化器通常输出连续权重，但交易系统下单是整数数量。
在换手上限和交易费存在时，这会变成组合优化中的离散难题。

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
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/discrete_rebalance_mip/verification/evaluate.py
```

使用 `frontier_eval` unified 任务运行：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/discrete_rebalance_mip \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

耗时说明：该任务包含混合整数规划（MIP）求解，耗时波动更大。`algorithm.iterations=0` 通常约 8-20 秒，在较慢 CPU 上可能更久。

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
