# Task: Hand-Written Control for SustainDC

## 1. Goal

Write a function that controls the three original SustainDC agents without training a model.

Your function receives the per-agent observation vectors produced by the original environment and returns one discrete action for each agent:

- `agent_ls`: load shifting
- `agent_dc`: data center cooling
- `agent_bat`: battery charging/discharging

You will edit:

`baseline/solution.py`

The required entry point is:

```python
def decide_actions(observations) -> dict:
    ...
```

Optional:

```python
def reset_policy() -> None:
    ...
```

If you want memory across timesteps, store it inside module-level variables and clear it in `reset_policy()`.

## 2. What problem are you actually solving?

SustainDC simulates a data center that must make three coupled decisions every 15 minutes:

1. Should flexible computing jobs be executed now or delayed?
2. Should cooling be increased, kept unchanged, or relaxed?
3. Should the battery charge, discharge, or stay idle?

These decisions interact:

- delaying work changes future server load
- server load changes cooling demand
- cooling and IT demand change grid power draw
- grid power draw and battery usage determine carbon emissions

So this is not three independent tasks. It is one joint control problem split into three original agents.

## 3. What you should optimize

The benchmark mainly rewards reductions in:

- carbon emissions
- water usage

while avoiding unsafe or low-quality task handling:

- dropped tasks
- overdue tasks

The fixed baseline reference is a `noop` controller:

- `agent_ls = 1`
- `agent_dc = 1`
- `agent_bat = 2`

Your score measures how much you improve over that reference on the fixed evaluation scenarios.

## 4. Function input and output

## Input

`decide_actions(observations)` receives a dictionary:

```python
{
    "agent_ls": np.ndarray(shape=(26,)),
    "agent_dc": np.ndarray(shape=(14,)),
    "agent_bat": np.ndarray(shape=(13,)),
}
```

These arrays are the real observation vectors created by `sustaindc_env.py`.

## Output

Return a dictionary:

```python
{
    "agent_ls": int,
    "agent_dc": int,
    "agent_bat": int,
}
```

Each value must be a valid discrete action.

## 5. Action meanings

## `agent_ls` actions

- `0`: defer flexible jobs into the queue
- `1`: keep the queue unchanged
- `2`: execute jobs from the queue

## `agent_dc` actions

- `0`: decrease cooling setpoint, which means more cooling
- `1`: keep cooling setpoint unchanged
- `2`: increase cooling setpoint, which means less cooling

## `agent_bat` actions

- `0`: charge the battery
- `1`: discharge the battery
- `2`: keep the battery idle

## 6. Observation semantics

The observations are partially observable summary features. You do **not** get every internal simulator variable.

## `agent_ls` observation, shape `(26,)`

| Index | Meaning |
|---|---|
| 0 | cosine of hour-of-day |
| 1 | sine of hour-of-day |
| 2 | current normalized carbon intensity |
| 3 | slope of near-future carbon intensity |
| 4 | slope of recent past carbon intensity |
| 5 | mean of near-future carbon intensity |
| 6 | std of near-future carbon intensity |
| 7 | current carbon percentile-like feature |
| 8 | normalized time to next carbon peak |
| 9 | normalized time to next carbon valley |
| 10 | oldest queued task age, normalized by 24 hours |
| 11 | average queued task age, normalized by 24 hours |
| 12 | queue fill ratio |
| 13 | current workload level |
| 14 | current normalized outdoor temperature |
| 15 | slope of near-future temperature |
| 16 | mean of near-future temperature |
| 17 | std of near-future temperature |
| 18 | current temperature percentile-like feature |
| 19 | normalized time to next temperature peak |
| 20 | normalized time to next temperature valley |
| 21 | fraction of queued tasks aged 0-6 hours |
| 22 | fraction of queued tasks aged 6-12 hours |
| 23 | fraction of queued tasks aged 12-18 hours |
| 24 | fraction of queued tasks aged 18-24 hours |
| 25 | fraction of queued tasks older than 24 hours |

Useful intuition:

- high `2` means the grid is dirty now
- high `5` means the near future is dirty on average
- high `12`, `10`, or `25` means queue pressure is building

## `agent_dc` observation, shape `(14,)`

| Index | Meaning |
|---|---|
| 0 | cosine of hour-of-day |
| 1 | sine of hour-of-day |
| 2 | current normalized carbon intensity |
| 3 | slope of near-future carbon intensity |
| 4 | slope of recent past carbon intensity |
| 5 | mean of near-future carbon intensity |
| 6 | std of near-future carbon intensity |
| 7 | current carbon percentile-like feature |
| 8 | normalized time to next carbon peak |
| 9 | normalized time to next carbon valley |
| 10 | current workload level |
| 11 | next-step workload level |
| 12 | current normalized outdoor temperature |
| 13 | next-step normalized outdoor temperature |

Useful intuition:

- high workload and high outdoor temperature usually mean cooling pressure is high
- high carbon intensity suggests reducing unnecessary cooling load when safe

## `agent_bat` observation, shape `(13,)`

| Index | Meaning |
|---|---|
| 0 | cosine of hour-of-day |
| 1 | sine of hour-of-day |
| 2 | current normalized carbon intensity |
| 3 | slope of near-future carbon intensity |
| 4 | slope of recent past carbon intensity |
| 5 | mean of near-future carbon intensity |
| 6 | std of near-future carbon intensity |
| 7 | current carbon percentile-like feature |
| 8 | normalized time to next carbon peak |
| 9 | normalized time to next carbon valley |
| 10 | current workload level |
| 11 | current normalized outdoor temperature |
| 12 | battery state of charge, in `[0, 1]` |

Useful intuition:

- if carbon is low now and high later, charging may help
- if carbon is high now and the battery already has energy, discharging may help
- aggressive charging can backfire because charging itself increases grid draw

## 7. Fixed evaluation scenarios

The benchmark uses four fixed scenarios:

- `az_july`: Arizona summer
- `ca_april`: California spring
- `ny_january`: New York winter
- `tx_august`: Texas late summer

Each scenario runs for `2` simulated days, and each day has `96` control steps, so one full benchmark run evaluates:

- `4 scenarios`
- `192 steps per scenario`
- `768 steps total`

The month index follows the repository convention:

- `0 = January`
- `11 = December`

## 8. Metrics collected during evaluation

For each episode, the evaluator accumulates:

- `carbon_kg`: total carbon footprint
- `water_l`: total water usage
- `dropped_tasks`: total dropped tasks
- `overdue_tasks`: accumulated overdue-task penalty
- `grid_energy_kwh`: total grid energy used

The score uses only the first four items directly, but `grid_energy_kwh` is also reported because it is useful for debugging.

## 9. Scoring

The score compares your policy against the `noop` reference on the same fixed scenario.

First compute relative improvements:

```text
carbon_gain = max(0, 1 - candidate_carbon / noop_carbon)
water_gain  = max(0, 1 - candidate_water  / noop_water)
```

To make repeated runs more stable, gains smaller than `0.2%` are treated as evaluation noise and rounded down to `0`.

Then compute a weighted improvement fraction:

```text
improvement_fraction = 0.85 * carbon_gain + 0.15 * water_gain
```

Then turn that into a score:

```text
base_score = 100 * sqrt(improvement_fraction)
safety_penalty = 5 * dropped_tasks + 0.5 * overdue_tasks
final_score = clip(base_score - safety_penalty, 0, 100)
```

### Interpretation

- `0` means you did not beat the `noop` reference
- a positive score means you improved resource efficiency without task-quality collapse
- `100` is the mathematical ceiling of the scoring rule

Important:

- `100` is **not** a proven globally optimal environment policy
- it is only the exact ceiling of this benchmark's normalized score

## 10. Expected result

The provided baseline currently scores about:

`7.9 / 100`

on the benchmark scenarios, with small run-to-run drift from the simulator.

The baseline is intentionally weak and simple. You should treat it as a starting point, not as a strong target.

## 11. Recommended path for improving the baseline

If you are new to the task, this is the easiest path:

1. Improve `agent_ls` first.
2. Keep `agent_dc` conservative at the beginning.
3. Leave `agent_bat` idle until you understand when charging actually helps.

Why?

- workload shifting already gives measurable gains
- battery policies are easy to make worse because charging consumes energy immediately
- cooling policies can reduce water but can also increase carbon if they trigger more IT or HVAC load in the wrong regime

## 12. Practical coding advice

- Start with thresholds and `if/else` rules.
- Print or inspect `verification/last_eval.json` after each run.
- Watch raw metrics, not only the final score.
- If your score collapses, check whether `dropped_tasks` or `overdue_tasks` became positive.
- If carbon gets worse, your battery or cooling rule is probably too aggressive.

## 13. Minimal example

```python
def decide_actions(observations):
    return {
        "agent_ls": 1,
        "agent_dc": 1,
        "agent_bat": 2,
    }
```

That is a valid policy, but it will only match the `noop` reference and therefore score around `0`.

## 14. How to run the evaluator

```bash
python verification/evaluate.py
```

Optional:

```bash
python verification/evaluate.py \
  --solution path/to/your_solution.py
```

If your upstream `dc-rl` clone is not in the sibling `sustaindc/` directory:

```bash
python verification/evaluate.py \
  --sustaindc-root /absolute/path/to/dc-rl
```

## 15. What success looks like

A good submission for this benchmark:

- is easy to read
- uses the observation features intentionally
- improves carbon and/or water over the `noop` controller
- avoids dropped and overdue tasks

You do **not** need machine learning to participate in this benchmark.
