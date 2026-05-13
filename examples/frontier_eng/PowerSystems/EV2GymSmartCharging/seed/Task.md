# Task: EV2GymSmartCharging

Design a charging policy for a fixed set of upstream-aligned `EV2Gym` workplace simulations.
At each step, output one normalized charging/discharging action per charging port.

## Objective

Maximize the upstream `EV2Gym` `total_reward` across three deterministic cases based on official `V2GProfitPlusLoads.yaml` data and logic.

## Inputs exposed to the policy

The policy receives a stepwise `case` dictionary containing:

- charging-port state
- EV battery, power, and departure fields
- transformer loading fields
- current and future electricity prices
- current power usage and power setpoint

## Output format

Return either:

```python
{"actions": [...]} 
```

or a raw action list that can be coerced to a one-dimensional vector with one action per port.
All actions must stay within `[-1, 1]`.

## Fixed evaluation cases

- `workplace_winter_48cs_3tr`
- `workplace_spring_64cs_4tr`
- `workplace_autumn_96cs_5tr`

## Reference source

- https://github.com/StavrosOrf/EV2Gym


