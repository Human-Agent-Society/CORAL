# EV2GymSmartCharging

这个 benchmark 把真实的 `EV2Gym` 智能充放电任务贡献到 `PowerSystems` 域中。
它直接使用上游 `EV2Gym` 模拟器和上游数据副本，而不是手写近似器。

## 上游来源

- GitHub：https://github.com/StavrosOrf/EV2Gym
- 本任务使用的上游配置模板：`references/upstream/V2GProfitPlusLoads.yaml`
- evaluator 实际使用的上游数据副本位于 `references/upstream/`

## 评测内容

评测脚本会在真实上游 `EV2Gym` 环境中运行三个固定 workplace case，这些 case 都从官方 `V2GProfitPlusLoads.yaml` 派生：

- `workplace_winter_48cs_3tr`：48 个充电站，3 个变压器，seed 17，时间 2022-01-17 05:00
- `workplace_spring_64cs_4tr`：64 个充电站，4 个变压器，seed 29，时间 2022-04-18 05:00
- `workplace_autumn_96cs_5tr`：96 个充电站，5 个变压器，seed 43，时间 2022-10-10 05:00

这些固定 case 会产生大约 30–100 个 EV 会话，同时保持评测时间可接受。

## 候选程序接口

只需要修改 `scripts/init.py`。
评测器会在每个时间步调用：

```python
solve(case, max_sim_calls=0, simulate_fn=None)
```

其中 `case` 会提供当前 EV2Gym 状态快照，包括：

- 每个充电口状态
- EV 电池与离站信息
- 变压器负载信息
- 当前与未来电价
- 当前总功率与 power setpoint

函数需要返回当前时间步每个充电口的归一化动作，范围必须在 `[-1, 1]` 内。

## 评分方式

- 单次 rollout 指标使用上游 EV2Gym 的 `total_reward`
- 最终分数为三个固定 case 的基线归一化平均分
- 官方上游启发式 `ChargeAsFastAsPossibleToDesiredCapacity` 被归一化为 `100`

## 附带方案

- `scripts/init.py`：与上游 `ChargeAsFastAsPossible` 对齐的可行初始策略
- `baseline/solution.py`：与官方 `ChargeAsFastAsPossibleToDesiredCapacity` 对齐的 baseline

## 本地运行

```bash
python benchmarks/PowerSystems/EV2GymSmartCharging/verification/evaluator.py \
  benchmarks/PowerSystems/EV2GymSmartCharging/scripts/init.py
```

```bash
python -m frontier_eval task=unified \
  task.benchmark=PowerSystems/EV2GymSmartCharging \
  task.runtime.use_conda_run=false \
  algorithm.iterations=0
```

