# PyMOTO SIMP 柔度优化

该任务是一个二维结构拓扑优化基准，目标是在固定体积分数约束下最小化结构柔度（compliance）。
基线实现采用受 pyMOTO 启发的 SIMP 流程，并使用可移植的 NumPy-only 实现：

- 密度滤波
- SIMP 材料插值
- 有限元刚度组装
- 线性方程求解
- 使用 OC 更新进行优化

## 目录结构

```text
PyMOTOSIMPCompliance/
├── README.md
├── Task.md
├── references/
│   └── problem_config.json
├── scripts/
│   └── init.py
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
└── frontier_eval/
    ├── initial_program.txt
    ├── candidate_destination.txt
    ├── eval_command.txt
    ├── eval_cwd.txt
    ├── constraints.txt
    ├── agent_files.txt
    ├── copy_files.txt
    ├── readonly_files.txt
    └── artifact_files.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线

```bash
cd benchmarks/StructuralOptimization/PyMOTOSIMPCompliance
python scripts/init.py
# 输出 temp/submission.json
```

### 3. 评测候选程序

```bash
cd benchmarks/StructuralOptimization/PyMOTOSIMPCompliance
python verification/evaluator.py scripts/init.py
```

## 提交格式

候选程序需写出 `temp/submission.json`：

```json
{
  "benchmark_id": "pymoto_simp_compliance",
  "nelx": 50,
  "nely": 16,
  "density_vector": [0.5, 0.5, 0.5],
  "compliance": 123.45,
  "volume_fraction": 0.5,
  "feasible": true
}
```

评测必需字段：

- `density_vector`（长度为 `nelx * nely`，即 `800` 的展平密度向量）

## 任务摘要

- **frontier_eval 任务名**: `pymoto_simp_compliance`
- **benchmark 路径**: `StructuralOptimization/PyMOTOSIMPCompliance`
- **网格**: `50 x 16`（800 个设计变量）
- **目标**: 最小化柔度
- **约束**: `mean(density) <= volfrac`（评测器带容差）
- **体积分数**: `0.5`
- **SIMP 惩罚系数**: `3.0`
- **滤波半径**: `2.0`
- **材料参数**: `E0=1.0`, `Emin=1e-9`, `nu=0.3`

## 评分方式

评测器会独立重算柔度，并按以下方式评分：

- 可行：`combined_score = baseline_uniform_compliance / compliance`
- 不可行：`combined_score = 0`, `valid = 0`

其中 `baseline_uniform_compliance` 是均匀密度场（`density = volfrac`）的柔度。
分数越高越好。

## 通过 frontier_eval 运行

```bash
python -m frontier_eval \
  task=pymoto_simp_compliance \
  algorithm=openevolve \
  algorithm.iterations=10
```

该任务通过 unified task 接口集成。

