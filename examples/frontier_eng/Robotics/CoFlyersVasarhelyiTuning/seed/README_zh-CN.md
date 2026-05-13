# CoFlyersVasarhelyiTuning

该 benchmark 基于 `CoFlyers` 原仓 `Prototype_Simulator` 中公开发布的 `Vasarhelyi_module/params_for_parallel` 参数组构建。

本任务并不直接调用原始 MATLAB/Simulink 运行时，而是提供了一个 **Python 重实现** 版本，用于复现核心群飞控制律和 `evaluation_0` 指标结构，以便统一接入 `Frontier-Engineering`。

## 来源

- 原始仓库：<https://github.com/micros-uav/CoFlyers>
- 原始全局配置：<https://github.com/micros-uav/CoFlyers/blob/main/matlab_simulink_ws/Prototype_Simulator/xml_config_files/parameters.xml>
- 原始 swarm 控制入口：<https://github.com/micros-uav/CoFlyers/blob/main/matlab_simulink_ws/Prototype_Simulator/lower_layers/swarm_module/Vasarhelyi_module/Vasarhelyi_module_generate_desire_i.m>
- 原始评估入口：<https://github.com/micros-uav/CoFlyers/blob/main/matlab_simulink_ws/Prototype_Simulator/lower_layers/evaluation_module/evaluation_0_module/evaluation_0_module_one.m>
- 原始 case 参数文件：`Vasarhelyi_module/params_for_parallel/Vasarhelyi_module_parameters_{1..8}.m`

## 文件结构

```text
CoFlyersVasarhelyiTuning/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── references/
│   └── coflyers_cases.json
├── scripts/
│   └── init.py
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
├── baseline/
│   ├── solution.py
│   └── result_log.txt
└── frontier_eval/
    ├── initial_program.txt
    ├── candidate_destination.txt
    ├── eval_command.txt
    ├── eval_cwd.txt
    ├── agent_files.txt
    ├── artifact_files.txt
    ├── constraints.txt
    └── readonly_files.txt
```

## 快速开始

在 benchmark 目录内直接运行评测：

```bash
python verification/evaluator.py scripts/init.py
```

在仓库根目录通过 unified `frontier_eval` 接口运行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Robotics/CoFlyersVasarhelyiTuning \
  task.runtime.use_conda_run=false \
  algorithm=openevolve \
  algorithm.iterations=0
```

## 提交接口

候选程序入口为 `scripts/init.py`，必须实现：

```python
def solve(problem: dict[str, Any]) -> dict[str, Any]:
    ...
```

推荐返回格式为：

```python
{"params": {...}}
```

也允许直接返回参数更新字典。评测器会将其与当前 case 的 `baseline_params` 合并，并裁剪到合法范围内。

## Benchmark 标识

- Unified benchmark 名称：`Robotics/CoFlyersVasarhelyiTuning`
- 可演化程序：`scripts/init.py`


