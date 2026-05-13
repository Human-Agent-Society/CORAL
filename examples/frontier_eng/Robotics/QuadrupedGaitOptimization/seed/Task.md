# Quadruped Gait Optimization

## 1. Background

Quadruped locomotion quality depends strongly on gait parameters (frequency, duty ratio, phase offsets, and stride geometry).

## 2. Task Setup

- Simulator: MuJoCo
- Model: self-contained ant-style quadruped in `references/ant.xml`
- Evaluation horizon: fixed-duration rollout (`8.0 s` by default)

## 3. Decision Variables

Submit the following 8 parameters in `submission.json`:

- `step_frequency` in `[0.5, 4.0]`
- `duty_factor` in `[0.30, 0.85]`
- `step_length` in `[0.04, 0.40]`
- `step_height` in `[0.02, 0.15]`
- `phase_FR` in `[0.0, 1.0)`
- `phase_RL` in `[0.0, 1.0)`
- `phase_RR` in `[0.0, 1.0)`
- `lateral_distance` in `[0.08, 0.20]`

## 4. Controller and Rollout

The evaluator maps gait parameters to open-loop leg targets, then applies joint-space PD control each simulation step.

## 5. Hard Constraints

Any of the following yields score `0.0`:

1. Parameter out of range.
2. Body roll or pitch exceeds configured threshold (`0.65 rad` default).
3. Actuator force exceeds configured limit (`1.0` default).
4. Forward progress below minimum threshold (`0.15 m` default).

## 6. Objective

Maximize average forward speed:

```
speed = (x_end - x_start) / duration
```

Higher is better.

## 7. Submission Format

```json
{
  "step_frequency": 1.8,
  "duty_factor": 0.62,
  "step_length": 0.16,
  "step_height": 0.07,
  "phase_FR": 0.5,
  "phase_RL": 0.5,
  "phase_RR": 0.0,
  "lateral_distance": 0.13
}
```

## 8. Evaluation Script

Use:

```bash
python verification/evaluator.py --submission submission.json
```

Output JSON:

```json
{"score": <float>, "feasible": <bool>}
```
