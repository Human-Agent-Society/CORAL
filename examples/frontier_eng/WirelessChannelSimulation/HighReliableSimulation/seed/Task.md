# HighReliableSimulation Task

## Objective

Estimate BER for Hamming(127,120) over AWGN in a rare-event regime.
You must implement `MySampler` and support variance-controlled simulation.

## Submission Contract

Submit one Python file that defines:

1. `class MySampler(SamplerBase)`
2. `MySampler.simulate_variance_controlled(...)` for local compatibility

Official scoring uses the benchmark-owned canonical simulation loop:

```python
sampler = MySampler(code=code, seed=seed)
result = code.simulate_variance_controlled(
    noise_std=DEV_SIGMA,
    target_std=TARGET_STD,
    max_samples=MAX_SAMPLES,
    sampler=sampler,
    batch_size=BATCH_SIZE,
    fix_tx=True,
    min_errors=MIN_ERRORS,
)
```

`code` is fixed by evaluator as `HammingCode(r=7, decoder="binary")` with `ChaseDecoder(t=3)`.
This avoids reward hacking through self-reported aggregate statistics returned by candidate wrappers.

## Return Format

`MySampler.simulate_variance_controlled(...)` may still return:

- Tuple/list with at least 6 fields:
  `(errors_log, weights_log, err_ratio, total_samples, actual_std, converged)`
- Dict with equivalent keys.

However, official scoring does not trust these self-reported aggregates; it recomputes them through the canonical benchmark loop above.

## Frozen Evaluation Constants

- `sigma = 0.268`
- `target_std = 0.05`
- `max_samples = 100000`
- `batch_size = 10000`
- `min_errors = 20`
- `r0 = 7.261287772505011e-07`
- `t0 = 10.4001037335396`
- `epsilon = 0.8`
- `repeats = 3`

## Scoring

- `e = |log(r / r0)|`, where `r = exp(err_rate_log)`.
- Let `s` be the median `actual_std` across repeats.
- If `e >= epsilon` or `s > target_std`, the run is invalid and receives `-1e18`.
- Otherwise: `score = t0 / (t * e + 1e-6)`, where `t` is median runtime.

## Failure Cases

Score is `-1e18` if any of the following happens:

- missing or invalid `MySampler` interface
- invalid or non-finite metrics from the canonical benchmark loop
- runtime failure
- median `actual_std` exceeds `target_std`
