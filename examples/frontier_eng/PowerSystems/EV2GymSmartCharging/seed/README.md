# EV2GymSmartCharging

This benchmark contributes a real `EV2Gym` smart-charging task to the `PowerSystems` domain.
It uses the upstream simulator and upstream data copies from `EV2Gym`, rather than a handcrafted surrogate.

## Upstream source

- GitHub: https://github.com/StavrosOrf/EV2Gym
- Upstream config template used here: `references/upstream/V2GProfitPlusLoads.yaml`
- Upstream data copies used by the evaluator live under `references/upstream/`

## What is evaluated

The evaluator runs the real upstream `EV2Gym` environment on three fixed workplace cases derived from the official `V2GProfitPlusLoads.yaml` setup:

- `workplace_winter_48cs_3tr` — 48 charging stations, 3 transformers, seed 17, 2022-01-17 05:00
- `workplace_spring_64cs_4tr` — 64 charging stations, 4 transformers, seed 29, 2022-04-18 05:00
- `workplace_autumn_96cs_5tr` — 96 charging stations, 5 transformers, seed 43, 2022-10-10 05:00

These fixed cases produce roughly 30–100 EV sessions while keeping the runtime manageable.

## Candidate interface

Edit `scripts/init.py` only.
The evaluator calls:

```python
solve(case, max_sim_calls=0, simulate_fn=None)
```

At each simulation step, `case` contains the current EV2Gym snapshot, including:

- charging-port state
- EV battery and departure information
- transformer loading information
- current and future prices
- current power usage and power setpoint

The function must return one normalized action per charging port in `[-1, 1]`.

## Scoring

- The rollout metric is the upstream EV2Gym `total_reward`
- Final benchmark score is the mean baseline-normalized reward across the three cases
- The official upstream heuristic `ChargeAsFastAsPossibleToDesiredCapacity` is normalized to score `100`

## Provided solutions

- `scripts/init.py`: feasible seed policy aligned with upstream `ChargeAsFastAsPossible`
- `baseline/solution.py`: official-style `ChargeAsFastAsPossibleToDesiredCapacity` baseline

## Run locally

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

