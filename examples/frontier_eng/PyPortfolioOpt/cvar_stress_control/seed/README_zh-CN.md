# 任务 02：CVaR 压力控制配置

该基准聚焦于“情景收益下的尾部风险优化”：
在收益门槛与暴露约束下，最小化组合 CVaR。

## 这个任务为什么重要

实盘组合常受回撤与压力测试指标约束。
在重尾市场中，仅用方差不足以描述风险，因此情景化 CVaR 优化在机构风控中很常见。

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
.venvs/frontier-v1-main/bin/python benchmarks/PyPortfolioOpt/cvar_stress_control/verification/evaluate.py
```

使用 `frontier_eval` unified 任务运行：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=PyPortfolioOpt/cvar_stress_control \
  task.runtime.env_name=frontier-v1-main \
  algorithm.iterations=0
```

耗时说明：该评测会在多个随机种子上重复求解 CVaR 优化问题。`algorithm.iterations=0` 的单次运行通常约 9-18 秒；做更长迭代时建议按分钟级预估总耗时。

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
