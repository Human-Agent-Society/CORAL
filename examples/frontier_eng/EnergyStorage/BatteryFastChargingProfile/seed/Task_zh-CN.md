# BatteryFastChargingProfile 任务说明

## 1. 背景

快充只有在安全且不会带来过高寿命损失时才真正有工程价值。工业界的电池管理系统在设计快充策略时，通常同时受三类机制限制：

- 高 SOC 区间的电压快速抬升，
- 欧姆热与极化损失带来的温升，
- 在大电流、低温或浓差较大时出现的析锂风险。

本任务用一个降阶的电-热-退化模型来刻画这些权衡，设计思路参考了工业实践中常见的分层体系：在线控制多用等效电路低阶模型，安全边界与快充机理分析则参考电化学 / 析锂感知模型。

## 2. 任务设定

你需要控制一颗锂离子电芯。电池与环境参数定义在：

- `references/battery_config.json`

当前示例配置为：

- 标称容量：`3.0 Ah`
- 初始 SOC：`0.10`
- 目标 SOC：`0.80`
- 环境温度：`25 C`
- 最大工作电压：`4.20 V`
- 硬安全截止电压：`4.25 V`
- 软温度限制：`45 C`
- 硬温度截止：`47 C`

用户后续可以直接修改 `references/battery_config.json`，以切换电芯规格、热环境或评分偏好，而不必改评测器代码。

评测器内部包含：

- 非线性 OCV 曲线，
- 与 SOC、温度相关的内阻，
- 极化状态，
- 浓差代理状态，
- 集总热模型，
- 析锂风险代理项，
- 类 SEI 的老化损失代理项。

## 3. 目标

最大化一个综合分数。该分数偏好：

- 更短的充电时间，
- 更低的峰值温度，
- 更低的析锂损失，
- 更低的老化损失。

评测器同时会输出各子指标，方便后续分析不同策略的 tradeoff。

## 4. 提交格式

提交一个 Python 文件，并定义：

```python
def build_charging_profile() -> dict:
    ...
```

返回格式如下：

```python
{
  "currents_c": [4.2, 3.0, 2.0, 1.1],
  "switch_soc": [0.32, 0.56, 0.72]
}
```

说明：

- `currents_c` 是各阶段的充电倍率（C-rate）。
- `switch_soc` 是各阶段切换的 SOC 阈值。
- 若共有 `N` 个阶段，则 `switch_soc` 长度必须为 `N - 1`。
- 评测器从 `SOC = 0.10` 开始，按当前倍率充电，达到阈值后切换到下一阶段。
- 当 `SOC >= 0.80` 时停止。

## 5. 约束

格式约束：

1. `1 <= len(currents_c) <= 6`
2. 每个倍率必须满足 `0.2 <= current <= 6.0`
3. `switch_soc` 必须严格递增
4. 每个阈值必须满足 `references/battery_config.json` 中配置的 SOC 边界

仿真约束：

1. 端电压不能超过 `4.25 V`
2. 电芯温度不能超过 `47 C`
3. 仿真必须在评测时长内达到 `SOC >= 0.80`

任何一条不满足都判为无效。

## 6. 评测

评测器使用确定性仿真，参数为：

- 时间步长与最大仿真时长由 `references/battery_config.json` 配置

输出指标包括：

- `charge_time_s`
- `max_temp_c`
- `max_voltage_v`
- `plating_loss_ah`
- `aging_loss_ah`
- `throughput_ah`
- `voltage_score`
- `combined_score`
- `valid`

### 评分规则

对于可行策略：

- `time_score` 随充电时间降低而提高
- `degradation_score` 随析锂与老化损失增大而降低
- `thermal_score` 随峰值温度升高而降低
- `voltage_score` 会在峰值电压超过配置中的软电压上限时下降

最终分数：

```text
combined_score = score_scale * (
  weight_time * time_score +
  weight_degradation * degradation_score +
  weight_thermal * thermal_score +
  weight_voltage * voltage_score
)
```

其中各项权重和缩放系数都从 `references/battery_config.json` 读取。

分数越高越好。

对于不可行策略：

- `valid = 0`
- `combined_score = 0`

## 7. 基线

`scripts/init.py` 和 `baseline/solution.py` 提供了一个较保守的多阶段恒流策略，可以安全到达目标 SOC，但在时间与寿命权衡上仍有优化空间。
