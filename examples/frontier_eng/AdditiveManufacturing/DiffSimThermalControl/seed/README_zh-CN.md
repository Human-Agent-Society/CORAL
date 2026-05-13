# DiffSim Thermal Control

这个任务把 `differentiable-simulation-am` 仓库中的真实增材制造构建 case 改造成了 Frontier-Engineering benchmark。

## 上游来源

本 benchmark 直接使用了上游仓库中已经提交的真实几何与刀路文件：

- `references/original/0.k`
- `references/original/toolpath.crs`

上游仓库：

- `https://github.com/mojtabamozaffar/differentiable-simulation-am`

需要特别说明的是：

- 上游 notebook 会读取 `data/target.npy` 和 `data/target_q.npy`；
- 但这两个文件并没有实际提交到仓库中；
- 因此这里的 benchmark 保留了原始真实几何、刀路和材料/工艺常数，并在此基础上定义了一个可复现的热过程控制目标。

## 任务意图

被 evolve 的仍然是一个基于梯度的工艺优化器，但现在 case 已经不是手工编造的 profile，而是从上游真实刀路中抽取出来的真实层级窗口。

当前任务优化的是若干归一化激光功率控制点，并在以下目标之间权衡：

- 跟踪目标热轨迹；
- 保持在 solidus / liquidus 工艺窗口内；
- 控制功率变化平滑；
- 保持合理的能量使用。

## 文件结构

```text
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   ├── result_log.txt
│   └── solution.py
├── frontier_eval/
│   ├── agent_files.txt
│   ├── candidate_destination.txt
│   ├── constraints.txt
│   ├── copy_files.txt
│   ├── eval_command.txt
│   ├── eval_cwd.txt
│   ├── initial_program.txt
│   └── readonly_files.txt
├── references/
│   ├── cases.json
│   └── original/
│       ├── 0.k
│       └── toolpath.crs
├── scripts/
│   └── init.py
└── verification/
    ├── evaluator.py
    └── requirements.txt
```

## Evolve 目标

- 被 evolve 的文件：`scripts/init.py`
- 参考基线实现：`baseline/solution.py`
- 允许修改的区域：`EVOLVE-BLOCK-START` 与 `EVOLVE-BLOCK-END` 之间

需要保持不变的接口：

- `load_cases(case_file=None)`
- `simulate(params, case)`
- `baseline_solve(case, max_sim_calls=..., simulate_fn=...)`
- `solve(case, max_sim_calls=..., simulate_fn=...)`

## 真实 Case

`references/cases.json` 当前定义了 4 个来自上游真实刀路层的 benchmark case：

- `toolpath_layer_01`
- `toolpath_layer_02`
- `toolpath_layer_27`
- `toolpath_layer_28`

每个 case 都基于以下真实信息构建：

- 真实路径坐标；
- 真实层高；
- 真实扫描时间；
- 上游 notebook 中使用的原始工艺常数。

## 如何运行

建议先安装本文档记录的验证依赖：

```bash
pip install -r verification/requirements.txt
```

在该任务目录中执行：

```bash
python verification/evaluator.py scripts/init.py
python verification/evaluator.py baseline/solution.py
```

如需输出文件：

```bash
python verification/evaluator.py scripts/init.py \
  --metrics-out metrics.json \
  --artifacts-out artifacts.json
```

从仓库根目录通过 unified 模式运行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=AdditiveManufacturing/DiffSimThermalControl \
  task.runtime.conda_env=<your_env> \
  algorithm.iterations=0
```

如果沿用这次本地验证使用的环境，把 `<your_env>` 替换成 `Engi`。

## 备注

- `verification/evaluator.py` 内部包含 canonical 评分路径。
- `baseline/result_log.txt` 保存了一次参考运行结果。

