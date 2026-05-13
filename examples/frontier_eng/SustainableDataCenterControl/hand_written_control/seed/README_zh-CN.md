# SustainDC `hand_written_control`

这个子任务要求你为 SustainDC 的三个原始 agent 编写一个确定性控制策略：

> **[注意] 必须完整克隆内部依赖目录才能运行本任务**：
> SustainDC 依赖前置的 `dc-rl` 库。本仓库的 `sustaindc` 文件夹是放置依赖的占位符。请在运行前执行：
> `git clone https://github.com/HewlettPackard/dc-rl.git benchmarks/SustainableDataCenterControl/hand_written_control/sustaindc`

或者直接使用仓库里的 bootstrap 入口：

```bash
python scripts/bootstrap/fetch_task_assets.py --target sustaindc
```

- `agent_ls`：负载迁移
- `agent_dc`：冷却控制
- `agent_bat`：电池调度

评测器会在四个固定场景上运行你的策略，并在同一次运行里和 noop 参考策略进行比较。

## 目录结构

```text
benchmarks/SustainableDataCenterControl/hand_written_control/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── benchmark_core.py
├── baseline/
│   └── solution.py
├── frontier_eval/
│   ├── agent_files.txt
│   ├── constraints.txt
│   ├── copy_files.txt
│   ├── eval_command.txt
│   └── ...
├── patches/
│   └── sustaindc_optional_runtime.patch
├── sustaindc/                # 仓库内自带的 dc-rl checkout，基于上游 commit a92b475
└── verification/
    ├── evaluate.py
    └── last_eval.json
```

## 环境准备

在仓库根目录执行：

```bash
bash init.sh
RUN_VALIDATION=0 bash scripts/env/setup_v1_task_envs.sh
```

如果要运行 unified task，还需要准备评测框架环境：

```bash
source .venvs/frontier-eval-driver/bin/activate
```

## 你需要修改哪里

只修改：

`baseline/solution.py`

必须保持 `decide_actions(observations) -> dict` 可用；`reset_policy()` 是可选的。

## Direct Verification

从仓库根目录运行：

```bash
.venvs/frontier-v1-sustaindc/bin/python benchmarks/SustainableDataCenterControl/hand_written_control/verification/evaluate.py
```

或者先进入子任务目录再运行：

```bash
cd benchmarks/SustainableDataCenterControl/hand_written_control
../../../.venvs/frontier-v1-sustaindc/bin/python verification/evaluate.py
```

在已验证环境上的实测耗时约为 `19.8s`。

评测器会把最近一次结构化结果写入 `verification/last_eval.json`。

## frontier_eval（Unified）

这个子任务已经通过 `frontier_eval/` 目录下的元数据接入 unified task。

从仓库根目录运行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=SustainableDataCenterControl/hand_written_control \
  task.runtime.env_name=frontier-v1-sustaindc \
  algorithm=openevolve \
  algorithm.iterations=0
```

在已验证环境上的实测耗时约为 `25.8s`。

耗时说明：即使设置 `algorithm.iterations=0`，unified 仍然会完整评测一次 `baseline/solution.py`，但在当前验证环境上明显低于默认的 `300s` timeout。

## 从全新上游 Clone 开始复现

这个目录里的 patch 已按上游 commit `a92b475` 做过校验。

```bash
cd benchmarks/SustainableDataCenterControl/hand_written_control

git clone https://github.com/HewlettPackard/dc-rl.git sustaindc_fresh
git -C sustaindc_fresh checkout a92b475

.venvs/frontier-v1-sustaindc/bin/python -m pip install -r sustaindc_fresh/requirements.txt
git -C sustaindc_fresh apply patches/sustaindc_optional_runtime.patch

.venvs/frontier-v1-sustaindc/bin/python verification/evaluate.py --sustaindc-root sustaindc_fresh
```

## 为什么需要这个 Patch

`patches/sustaindc_optional_runtime.patch` 只修改上游的 `sustaindc_env.py`。

它只解决 benchmark 运行时真正需要的问题：

- 把 `matplotlib` 变成可选依赖，因为这个 benchmark 不需要渲染绘图
- 把 dashboard 相关导入变成可选，因为上游 `requirements.txt` 默认并不会安装 dashboard 依赖
- 如果真的开启 render 模式，缺少这些依赖时会报更清晰的错误

## 说明

- 底层模拟器不是严格 bitwise deterministic 的，所以不同次运行之间出现少量分数波动是正常的。
- benchmark 会在同一次评测里同时运行你的策略和 noop 参考策略，再做比较。
- 如果你想看完整任务定义，请继续阅读 `Task.md` 或 `Task_zh-CN.md`。
