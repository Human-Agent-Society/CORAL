# BatteryFastChargingProfile Task

## 1. Background

Fast charging is valuable only when it is safe and does not induce excessive long-term damage. In industrial battery-management systems, charging policies are usually constrained by three interacting mechanisms:

- voltage rise near high SOC,
- cell heating caused by ohmic and polarization losses,
- lithium-plating risk under aggressive current, low temperature, or large concentration gradients.

This benchmark captures that tradeoff using a reduced-order electro-thermal-aging model inspired by the hierarchy used in practice: equivalent-circuit control models for online optimization, and electrochemical / plating-aware models for safety analysis.

## 2. Task Setup

You control a single lithium-ion cell. The battery and environment parameters are defined in:

- `references/battery_config.json`

The current example configuration uses:

- nominal capacity: `3.0 Ah`
- initial SOC: `0.10`
- target SOC: `0.80`
- ambient temperature: `25 C`
- maximum terminal voltage: `4.20 V`
- hard safety cutoff voltage: `4.25 V`
- soft thermal limit: `45 C`
- hard thermal cutoff: `47 C`

Users may replace the values in `references/battery_config.json` to define another cell, thermal environment, or scoring preference without editing evaluator code.

The evaluator simulates charging with a reduced-order model containing:

- nonlinear OCV curve,
- SOC- and temperature-dependent internal resistance,
- polarization state,
- concentration-gradient proxy,
- lumped thermal dynamics,
- lithium-plating risk proxy,
- SEI-like aging cost surrogate.

## 3. Objective

Maximize a scalar score that rewards:

- lower charging time,
- lower peak temperature,
- lower plating severity,
- lower aging loss.

The evaluator also exposes sub-metrics so different tradeoffs can be compared after the run.

## 4. Submission Contract

Submit one Python file that defines:

```python
def build_charging_profile() -> dict:
    ...
```

The returned dict must contain:

```python
{
  "currents_c": [4.2, 3.0, 2.0, 1.1],
  "switch_soc": [0.32, 0.56, 0.72]
}
```

Rules:

- `currents_c` is a list of charge rates in C.
- `switch_soc` is a list of strictly increasing SOC thresholds.
- If there are `N` current stages, `switch_soc` must have length `N - 1`.
- Each current applies until the corresponding threshold is reached, then the evaluator switches to the next current stage.
- Charging always starts at `SOC = 0.10` and stops once `SOC >= 0.80`.

## 5. Constraints

Profile-format constraints:

1. `1 <= len(currents_c) <= 6`
2. each current must satisfy `0.2 <= current <= 6.0`
3. `switch_soc` values must be strictly increasing
4. each threshold must satisfy the SOC bounds configured in `references/battery_config.json`

Simulation constraints:

1. terminal voltage must never exceed `4.25 V`
2. cell temperature must never exceed `47 C`
3. the simulation must reach `SOC >= 0.80` within the evaluation horizon

Any violation makes the candidate invalid.

## 6. Evaluation

The evaluator runs a deterministic simulation with:

- time step and horizon configured in `references/battery_config.json`

Returned metrics include:

- `charge_time_s`
- `max_temp_c`
- `max_voltage_v`
- `plating_loss_ah`
- `aging_loss_ah`
- `throughput_ah`
- `voltage_score`
- `combined_score`
- `valid`

### Scoring

For feasible profiles:

- `time_score` increases when charge time decreases
- `degradation_score` decreases with plating and aging loss
- `thermal_score` decreases with higher peak temperature
- `voltage_score` decreases when peak voltage exceeds the configured soft voltage limit

The final score is:

```text
combined_score = score_scale * (
  weight_time * time_score +
  weight_degradation * degradation_score +
  weight_thermal * thermal_score +
  weight_voltage * voltage_score
)
```

The weights and scaling factor are read from `references/battery_config.json`.

Higher is better.

For infeasible profiles:

- `valid = 0`
- `combined_score = 0`

## 7. Baseline

`scripts/init.py` and `baseline/solution.py` provide a conservative multi-stage constant-current policy. It reaches the target safely, but leaves room for better time / lifetime tradeoffs.
