# Threshold v2 operational pilot log

## Smooth/global B=128, held-out seed 1

The accepted retry finished on 2026-07-25 after approximately 44 minutes:

```text
run: budget-128/smooth128_rep_v2/global_8/rep-01-retry-01
real attempts: 128
per-agent attempts: 8 × 16
numeric scores: 128
initial-candidate errors: 0
invalid/parse errors: 1 (charged numeric zero)
auto-stop: max_real_attempts
best score: 0.6038879574
random z: 6.1826
```

The 300-second watchdog restarted stalled model sessions and eventually
recovered the quota, but progress was highly asynchronous: five agents had
already exhausted their 16 attempts while three remained at 1, 2, and 14.
This makes global-evaluation migration ticks vulnerable to runtime-speed
confounding even when the final quota is balanced.

More importantly, the natural global cell did not realize the champion-
takeover behavior used by the v2 positive calibration:

```text
local transition rate: 0.9580
operator entropy: 0.1844
cross-agent parent adoption rate: 0.0000
exact foreign copies: 0
final inferred lineages: 8
final candidate diversity: 0.4141
```

Agents independently converged on nearly the same local-search operator while
retaining different candidate lineages. Candidate Hamming diversity alone
would therefore miss strategy monoculture, while duplicate rate alone would
incorrectly suggest there was no convergence of method. This cell is a valid
operational pilot but is not a topology comparison and cannot support a claim
for or against multi-island search.

Threshold v3 responds by separating natural and explicit high-diffusion
policies, calibrating partial imitation rather than assuming takeover, using
actual move-not-copy migration, and reporting operator/coordinate/lineage
diagnostics as manipulation checks.
