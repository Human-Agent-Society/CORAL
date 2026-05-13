# 任务：EV2GymSmartCharging

为一组固定的、与上游 `EV2Gym` 对齐的 workplace 仿真实现充放电策略。
在每个时间步，你都要为每个充电口输出一个归一化充放电动作。

## 目标

在三个确定性 case 上，最大化上游 `EV2Gym` 的 `total_reward`。
这些 case 使用官方 `V2GProfitPlusLoads.yaml` 的数据与逻辑。

## 策略可见输入

策略会收到逐步的 `case` 字典，其中包含：

- 充电口状态
- EV 电池、功率与离站字段
- 变压器负载字段
- 当前与未来电价
- 当前总功率与 power setpoint

## 输出格式

返回：

```python
{"actions": [...]} 
```

或者任何可转换为一维动作向量的原始列表；向量长度必须等于充电口数量。
所有动作都必须落在 `[-1, 1]` 内。

## 固定评测 case

- `workplace_winter_48cs_3tr`
- `workplace_spring_64cs_4tr`
- `workplace_autumn_96cs_5tr`

## 参考来源

- https://github.com/StavrosOrf/EV2Gym


