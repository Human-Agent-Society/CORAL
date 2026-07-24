# Modular multi-island follow-up

Status: the modular-v1 and active-v2 runs are design audits, not topology
evidence. The harder v3 package below is the current candidate for a
confirmatory threshold study; it has not yet produced a conclusion.

The old NK cells remain useful black-box stress controls, but they do not
exercise the blog's stronger mechanism: carrying a tested sub-artifact and its
provenance between partially independent communities. This follow-up keeps a
literal-candidate interface while making the candidate an explicit collection
of modules.

## Why v1/v2 are not evidence

The first modular pilot returned every module score, so a cross-module bit probe
could decode the smooth target. The active-v2 pilot removed that feedback leak,
but its operator analyzer still counted exact bits that had never been selected
and tested, and its rugged codebook was readable from the agent-visible grader
source. Those runs are retained as design-audit evidence only.

## Hard v3 threshold package

`run_hard_matrix.py` runs `smooth_hard256` and `rugged_hard256`. Both tasks use
sixteen 16-bit modules in a 256-bit candidate and score only the declared
`ACTIVE_MODULE`. Eight independent private seeds are paired across topologies by
repetition.

* `smooth_hard256` retains Hamming feedback but doubles both the module count
  and width relative to the active-v2 task. A conservative coordinate-probe
  anchor is 272 evaluations for one complete artifact, so B=256/512 brackets
  its discovery threshold.
* `rugged_hard256` uses a public 256-code codebook and a private target index,
  with an all-zero trap and equality-only feedback. Ordered enumeration costs
  1,238–2,395 evaluations across the eight seeds, so B=1,024/2,048/4,096 is
  the intended threshold ladder.

The public codebook is deliberate: agents may enumerate it, while the target
index and seed remain private. This makes the rugged difficulty calibratable
instead of depending on whether an agent happens to read grader source.

`analyze_hard_active.py` makes provenance-backed assembly the primary metric.
An exact block counts only after an active real evaluation returned 1.0, and a
later candidate receives credit only when it carries those exact tested bits.
Untested lucky bits are retained as an oracle diagnostic but cannot count as
institutional discoveries.

## Protocol and analysis

`calibrate_hard.py` reports the per-seed difficulty anchors before any agent
run. A result is eligible for a topology contrast only after eight independent
seed repetitions per task/budget/topology pass the integrity audit. The primary
comparison is `multi_island - partition` (migration under the same number of
agents); `multi_island - global` is secondary because global uses fewer islands
and therefore fewer agents under the fixed total-evaluation budget.

The primary outcomes are provenance-backed exact-module count and assembled
score. The analyzer also reports a pooled-provenance score and the gap between
pooled and best-single-candidate assembly, separating failure to discover
modules from failure to transfer/assemble them. Oracle recomputation is a
secondary diagnostic, never a substitute for provenance.

## Files

```text
tasks/modular_landscape/             rejected v1 diagnostic package
tasks/active_modular_landscape/      v2 active-module design audit
tasks/hard_active_modular_landscape/ v3 hard seed-bundled package
run_matrix.py                        v1/v2 launcher
run_hard_matrix.py                   v3 budget-isolated launcher
calibrate_hard.py                    v3 operator-side threshold calibration
analyze_hard_active.py               v3 integrity and topology analysis
hard_eval_protocol.md                v3 agent-facing protocol
```
