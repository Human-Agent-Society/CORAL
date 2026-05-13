# BatteryFastChargingSPMe Task

## 1. Background

Extreme fast charging is a constrained optimal-control problem rather than a simple "charge as hard as possible" problem. In practice, high current improves time-to-target but simultaneously:

- increases electrolyte polarization,
- raises kinetic overpotential,
- pushes negative-electrode plating risk upward,
- elevates temperature,
- accelerates SEI-like aging.

This task uses a reduced `SPMe-T-Aging` style surrogate to expose those tradeoffs while remaining cheap enough for repeated benchmark evaluation.

## 2. Task Setup

You control a single lithium-ion cell with parameters defined in:

- `references/battery_config.json`

The example configuration describes:

- a `3.0 Ah` cell,
- charging from `SOC = 0.10` to `SOC = 0.90`,
- ambient temperature `25 C`,
- working voltage limit `4.20 V`,
- hard voltage cutoff `4.25 V`,
- soft temperature limit `43 C`,
- hard temperature cutoff `46 C`.

The evaluator maintains the following reduced internal states:

- negative electrode average and surface stoichiometry,
- positive electrode average and surface stoichiometry,
- electrolyte polarization state,
- lumped temperature,
- cumulative plating-loss and SEI-aging proxies.

## 3. Objective

Maximize a scalar score that rewards:

- shorter charging time,
- smaller SEI-aging loss,
- smaller plating loss / plating-margin violation,
- lower thermal stress.

## 4. Submission Contract

Submit one Python file that defines:

```python
def build_charging_policy() -> dict:
    ...
```

The returned dict must contain:

```python
{
  "currents_c": [5.4, 4.2, 2.8, 1.5],
  "switch_soc": [0.20, 0.48, 0.76]
}
```

Rules:

- `currents_c` is a list of charge rates in C.
- `switch_soc` is a list of strictly increasing SOC thresholds.
- If there are `N` current stages, `switch_soc` must have length `N - 1`.
- Charging starts at the configured initial SOC and stops once the configured target SOC is reached.

## 5. Constraints

Profile-format constraints:

1. stage count must stay within `references/battery_config.json`
2. each current must lie within configured current bounds
3. `switch_soc` must be strictly increasing
4. each threshold must lie within configured SOC bounds

Simulation constraints:

1. terminal voltage must never exceed the hard cutoff
2. cell temperature must never exceed the hard cutoff
3. plating margin must never fall below the configured hard margin
4. the simulation must reach the configured target SOC within the configured horizon

Any violation makes the candidate invalid.

## 6. Evaluation

The evaluator uses a reduced electrochemical-thermal-aging simulation with:

- solid-state surface dynamics for both electrodes,
- electrolyte polarization dynamics,
- current-dependent kinetic overpotentials,
- lumped thermal dynamics,
- plating-margin and SEI-aging surrogates.

All model coefficients, safety limits, and scoring weights are configured in:

- `references/battery_config.json`

Returned metrics include:

- `charge_time_s`
- `max_temp_c`
- `max_voltage_v`
- `min_plating_margin_v`
- `plating_loss_ah`
- `aging_loss_ah`
- `time_score`
- `aging_score`
- `plating_score`
- `thermal_score`
- `voltage_score`
- `combined_score`
- `valid`

### Scoring

The final score is a weighted combination of:

- time-to-target,
- aging loss,
- plating stress,
- soft voltage excursion,
- thermal stress.

Higher is better.

## 7. Benchmark Interpretation

This task is a reduced-order physical-model benchmark:

- more physically structured than a pure equivalent-circuit task,
- much cheaper than a full P2D / DFN electrochemical solver,
- suitable for staged charging-policy optimization with AI agents.
