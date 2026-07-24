# Modular multi-island follow-up

Status: the modular-v1, active-v2, v3, and v4 runs are design audits, not
topology evidence. v5 is also retained as an audit because its assembly metric
was operator-side. The v6 verified-assembly package below is the current
candidate for a threshold study; it has not yet produced a conclusion.

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

## Hard v4 threshold package

`run_hard_v4.py` is the next independent package. It uses 24×24-bit modules,
tuple-form candidates, a 512-entry rugged codebook with unique per-seed
targets, and a `global_8` control that holds the eight-agent roster fixed.
`analyze_hard_v4.py` adds malformed-candidate, mode/seed, migration, and
module-coverage gates. The v4 research design and calibration are in
`research_design_v4.md` and `hard_v4_calibration.json`.
An audit found that v4's partitioned conditions had four total agents (two per
island), so its fixed-eight-agent secondary comparison is invalid; v4 remains
design-audit material.

## Hard v5 threshold package

`run_hard_v5.py` is an independent higher-dimensional package. It uses
32×32-bit modules (1,024 bits), a 1,024-entry rugged codebook, unique private
targets, and the same-roster `global_8` control. Smooth provenance cost is
1,088 evaluations for a full artifact; rugged ordered enumeration costs
13,018–18,917 across the frozen seeds. The ladder is smooth
256/512/1,024/1,536 and rugged 4,096/8,192/16,384/24,576. The rugged decoy is
below a wrong nonzero proposal so migration selection does not reward a
stalled agent. See `research_design_v5.md`, `hard_v5_calibration.json`, and
`hard_v5_eval_protocol.md`.

## Hard v6 verified-assembly package

`run_hard_v6.py` is the current research package. It uses 48×32-bit modules,
an observable exact-module assembly reward, a 2,048-entry rugged codebook, and
origin-preserving migration provenance. Smooth has a 1,632-evaluation
coordinate/provenance anchor; rugged ordered enumeration costs about
45.5k–57.5k evaluations across the paired seeds. The staged ladder is smooth
512/1,024/1,536/2,048/3,072 and rugged 8,192/16,384/32,768/49,152/65,536.

The analyzer's primary outcomes come from the grader's assembly feedback, not
only retrospective reconstruction. `research_design_v6.md` specifies the
gates, transfer diagnostics, and communication ablation required before any
institutional interpretation. The v6 runner also fixes a sparse 16/32
heartbeat cadence across all topologies; the normal per-eval reflection
heartbeat is an operational confound for fixed-budget threshold cells.

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
run_hard_v5.py                       v5 high-dimensional launcher
calibrate_hard_v5.py                 v5 threshold calibration
analyze_hard_v5.py                   v5 integrity/provenance analyzer
hard_v5_eval_protocol.md             v5 agent-facing protocol
run_hard_v6.py                        v6 verified-assembly launcher
calibrate_hard_v6.py                  v6 difficulty calibration
analyze_hard_v6.py                    v6 observed assembly/transfer analyzer
hard_v6_eval_protocol.md              v6 agent-facing protocol
```
