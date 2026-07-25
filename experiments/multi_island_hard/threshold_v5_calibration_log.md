# Threshold-v5 hard-Smooth calibration result

The complete calibration joins a new hidden-target, hidden-coordinate-order
Permuted LeadingOnes control to the frozen v4 N=512 NK grid on the same eight
calibration landscapes, four paired policy seeds, three budgets, three
topologies, and four mutation policies.  The generated result is
`threshold_v5_hard_smooth_calibration.json` (SHA-256
`768960841c870b954bd21fda73e06e8975e37c58dc0a686e7a582035bd75cefa`).
`fully_registered_run` is true.

The first cell passing every local-operator gate remains K=64/B=16,384.  For
one-bit, registered-mixed, and broader-local mutation, multi-island beats both
global and permanent partition on Rugged, the original within-NK
Rugged-minus-Smooth interaction passes, Permuted LeadingOnes is unsolved, and
has the opposite topology direction.

For registered-mixed Permuted LeadingOnes, global's mean/max solved prefix and
exact solution count are:

| budget | mean prefix | max prefix | exact solutions / 32 |
| ---: | ---: | ---: | ---: |
| 4,096 | 22.7 | 39 | 0 |
| 8,192 | 40.4 | 61 | 0 |
| 16,384 | 71.2 | 91 | 0 |

This resolves the additive K=0 saturation problem without pretending that two
different landscape families share a comparable random-z scale.  The result
selects a scripted mechanism anchor only; no held-out performance result,
natural-agent run, or blog outcome entered the calibration.

The earlier ordinary-LeadingOnes B=256 smoke and interrupted B=1,024 launch
are invalid task-design records, not negative-result evidence.  The public
coordinate order exposed an O(N) adaptive shortcut.  The held-out real-CORAL
phase ladder must therefore restart with Permuted LeadingOnes at
B=256/1,024/4,096/8,192/16,384.
