# OpenFF Optimization Tasks

## 目录结构

```text
MolecularMechanics/
├── README.md
├── README_zh-CN.md
├── requirements.txt
├── Task.md
├── Task_zh-CN.md
├── frontier_eval/
│   └── run_eval.py
├── weighted_parameter_coverage/
│   ├── Task.md
│   ├── Task_zh-CN.md
│   ├── baseline/
│   │   └── init.py
│   ├── data/
│   │   └── raw_task.json
│   ├── frontier_eval/
│   │   ├── initial_program.txt
│   │   ├── eval_command.txt
│   │   └── ...
│   └── verification/
│       └── evaluate.py
├── diverse_conformer_portfolio/
│   ├── Task.md
│   ├── Task_zh-CN.md
│   ├── baseline/
│   │   └── init.py
│   ├── data/
│   │   └── raw_task.json
│   ├── frontier_eval/
│   │   ├── initial_program.txt
│   │   ├── eval_command.txt
│   │   └── ...
│   └── verification/
│       └── evaluate.py
└── torsion_profile_fitting/
    ├── Task.md
    ├── Task_zh-CN.md
    ├── baseline/
    │   └── init.py
    ├── data/
    │   └── raw_task.json
    ├── frontier_eval/
    │   ├── initial_program.txt
    │   ├── eval_command.txt
    │   └── ...
    └── verification/
        └── evaluate.py
```

## 每个任务目录里的文件含义

- `Task.md`
  - 英文任务说明
- `Task_zh-CN.md`
  - 中文任务说明
- `baseline/init.py`
  - starter 解法
  - 尽量只做优化，不直接依赖化学库
- `data/raw_task.json`
  - 原始任务配置
- `verification/evaluate.py`
  - `prepare` 和 `evaluate` 入口
- `frontier_eval/`
  - unified task 元数据
  - 让 `python -m frontier_eval` 可以直接评测该子任务

## 环境配置

推荐把框架运行环境和 benchmark 运行环境分开：

- `.venvs/frontier-eval-driver`
  - 用来运行 `python -m frontier_eval`
- `openff-dev`
  - 一个单独 bootstrap 的运行时，用来执行 MolecularMechanics 的真实评测

推荐直接在仓库根目录执行：

```bash
bash init.sh
bash scripts/bootstrap/install_openff_dev.sh
source .venvs/frontier-eval-driver/bin/activate
```

如果你已经有这两个运行时，直接在仓库根目录执行：

```bash
bash init.sh
source .venvs/frontier-eval-driver/bin/activate
.venvs/openff-dev/bin/python -m pip install -r benchmarks/MolecularMechanics/requirements.txt
./.venvs/openff-dev/bin/python scripts/bootstrap/verify_openff_dev.py --repo-root .
```

`openff-dev` 之所以仍然单独作为特殊 runtime 处理，是因为截至 2026 年，OpenFF 这条依赖链还不能通过 `uv` 单独完整复现。

仓库提供的 bootstrap 会用 `mamba`/`conda-forge` 把这个运行时装到 `.venvs/openff-dev`，并在安装后跑一次 smoke 验证：

```bash
bash scripts/bootstrap/install_openff_dev.sh
```

说明：

- `benchmarks/MolecularMechanics/requirements.txt`
  - 放的是 Python 层依赖
- `rdkit`、`openmm`、`ambertools`
  - 仍然通过 `mamba`/`conda-forge` 这一侧安装更稳妥
- 如果你只手工运行某个子任务
  - `.venvs/openff-dev` 就够了
- 如果你通过 `frontier_eval` 运行
  - 框架进程在 `frontier-eval-driver`
  - benchmark 评测进程会自动切到 `openff-dev`

## Frontier Eval（Unified）

这 3 个子任务都已经通过 unified task 接入 `frontier_eval`。

快捷 task 名如下：

| 子任务 | 快捷 task 名 | 等价 benchmark 路径 | `algorithm.iterations=0` 实测耗时 |
|---|---|---|---|
| `weighted_parameter_coverage` | `molecular_mechanics_weighted_parameter_coverage` | `MolecularMechanics/weighted_parameter_coverage` | 约 `5.6s` |
| `diverse_conformer_portfolio` | `molecular_mechanics_diverse_conformer_portfolio` | `MolecularMechanics/diverse_conformer_portfolio` | 约 `5.5s` |
| `torsion_profile_fitting` | `molecular_mechanics_torsion_profile_fitting` | `MolecularMechanics/torsion_profile_fitting` | 约 `26.8s` |

上表耗时来自 `2026-03-16` 的实测，命令均为：

- `.venvs/frontier-eval-driver/bin/python -m frontier_eval ...`
- `algorithm=openevolve`
- `algorithm.iterations=0`
- benchmark runtime 环境为 `openff-dev`

快速运行：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_weighted_parameter_coverage \
  algorithm=openevolve \
  algorithm.iterations=0

.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_diverse_conformer_portfolio \
  algorithm=openevolve \
  algorithm.iterations=0

.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=molecular_mechanics_torsion_profile_fitting \
  algorithm=openevolve \
  algorithm.iterations=0
```

等价的显式 unified 命令示例：

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=MolecularMechanics/torsion_profile_fitting \
  task.runtime.python_path=uv-env:openff-dev \
  algorithm=openevolve \
  algorithm.iterations=0
```

## 手工运行方式

每个任务都遵循同一套三步流程：

1. `prepare`
   - 从 `data/raw_task.json` 生成算法输入
2. 运行 `baseline/init.py`
   - 产生一个候选解
3. `evaluate`
   - 用真实规则打分

下面以 `weighted_parameter_coverage` 为例。

如果从任务目录运行：

```bash
cd benchmarks/MolecularMechanics/weighted_parameter_coverage
mkdir -p outputs

python verification/evaluate.py prepare \
  --raw-task data/raw_task.json \
  --prepared-output outputs/prepared.json

python baseline/init.py \
  --prepared-input outputs/prepared.json \
  --solution-output outputs/solution.json

python verification/evaluate.py evaluate \
  --prepared-input outputs/prepared.json \
  --solution outputs/solution.json \
  --result-output outputs/result.json
```

如果从仓库根目录运行：

```bash
mkdir -p benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs

python benchmarks/MolecularMechanics/weighted_parameter_coverage/verification/evaluate.py prepare \
  --raw-task benchmarks/MolecularMechanics/weighted_parameter_coverage/data/raw_task.json \
  --prepared-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json

python benchmarks/MolecularMechanics/weighted_parameter_coverage/baseline/init.py \
  --prepared-input benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json \
  --solution-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/solution.json

python benchmarks/MolecularMechanics/weighted_parameter_coverage/verification/evaluate.py evaluate \
  --prepared-input benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/prepared.json \
  --solution benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/solution.json \
  --result-output benchmarks/MolecularMechanics/weighted_parameter_coverage/outputs/result.json
```

另外两道题完全同理，只需要把目录名替换成：

- `diverse_conformer_portfolio`
- `torsion_profile_fitting`

## 耗时说明

- `weighted_parameter_coverage`
  - 单次 unified 评测约 `5-6s`
- `diverse_conformer_portfolio`
  - 单次 unified 评测约 `5-6s`
- `torsion_profile_fitting`
  - 单次 unified 评测约 `25-30s`
  - 主要耗时在 `prepare` 阶段的 torsion scan 和 profile 计算

如果你后续用多轮优化算法反复调用评测器，`torsion_profile_fitting` 的总耗时会明显高于另外两题。

## 建议阅读顺序

1. 先看 [Task_zh-CN.md](Task_zh-CN.md)
2. 再看具体任务目录下的 `Task_zh-CN.md`
3. 最后看对应的 `baseline/init.py`
