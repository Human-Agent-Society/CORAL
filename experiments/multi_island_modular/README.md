# Modular multi-island follow-up

Status: the modular-v1 through v7 runs are design or operational audits, not
topology evidence. v6 exposed an inactive exact-module count. v7 removed that
oracle, but its pooled primary outcome performed an impossible operator-side
cross-island assembly for `partition`, while deterministic disjoint lanes made
discovery nearly topology-invariant. The certified-composition v8 package is
the replacement threshold study; it must pass scripted treatment-sensitivity
checks before any LLM matrix is launched.

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

v6 is retained as a mechanism audit because `artifact_exact_count` can be
differenced across inactive-module edits and therefore acts as an unintended
group-testing signal. A v6 score difference cannot isolate migration from that
extra feedback channel. The incomplete B=1024 run, its throughput imbalance,
and the analyzer bugs found during inspection are recorded in
`hard_v6_operational_audit.md`.

## Hard v7 oracle-free threshold package

`run_hard_v7.py` doubles module width to 64 bits, keeps 48 modules, and grows
the rugged public codebook to 4,096 entries. Smooth's full provenance anchor is
3,168 evaluations; rugged ordered enumeration costs 80,146–111,613 across the
eight paired seeds. The staged ladder is smooth
1,024/2,048/3,072/4,096/6,144/8,192 and rugged
16,384/32,768/65,536/98,304/131,072/196,608.

Only the selected module is scored during search. Offline chronological
provenance remains the primary assembly metric, so inactive exact-count
differencing cannot guide the agents. `analyze_hard_v7.py` also reports an
agent-quota gate in addition to coverage, exact-signal, and migration gates;
the runner atomically reserves exactly one eighth of the global budget for
each agent, and quota-failing cells remain operational audits. See
`research_design_v7.md`, `hard_v7_calibration.json`,
`hard_v7_eval_protocol.md`, and the staged operational record in
`hard_v7_pilot_log.md`.

Post-pilot review stopped v7 before a third launch. Its run-wide
`final_known_blocks` union is not a feasible artifact produced by an island,
and its equality-only Rugged search plus fixed lanes leaves migration almost no
way to change discovery. `research_design_v7.md` now records the superseded
status. v7 remains useful only for testing quotas, numeric failure handling,
migration mechanics, and chronology-backed diagnostics.

## Hard v8 certified-composition package

`run_hard_v8.py` replaces pooled operator assembly with portable exact
certificates and an actual-submission primary outcome. It is a migration
mechanism positive control, not standalone evidence for endogenous
institution-building. Both tasks contain
32×32-bit modules. Smooth has a 1,088-evaluation full-artifact upper bound.
Rugged contains four private random 8-bit sublandscapes per module, about 28
strict one-bit local maxima per group in the frozen seeds, and a 32,800-
evaluation exhaustive upper bound. The registered ladders bracket discovery,
discovery without a later migration, and migration followed by a real
consolidation submission.

Run `simulate_hard_v8.py` before spending agent budget. Its deterministic
positive-control policy must show no pre-transfer topology difference, no
cross-island union in `partition`, and a post-transfer window in both tasks.
`analyze_hard_v8.py` then audits certificate integrity and treats global pooled
discovery as a diagnostic only. See `research_design_v8.md`,
`hard_v8_calibration.json`, and `hard_v8_eval_protocol.md`.

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
run_hard_v7.py                        v7 oracle-free high-difficulty launcher
calibrate_hard_v7.py                  v7 difficulty calibration
analyze_hard_v7.py                    v7 provenance/transfer/quota analyzer
hard_v7_eval_protocol.md              v7 agent-facing protocol
run_hard_v8.py                        v8 certified-composition launcher
calibrate_hard_v8.py                  v8 ruggedness/difficulty calibration
simulate_hard_v8.py                   v8 treatment-sensitivity preflight
analyze_hard_v8.py                    v8 submitted-artifact/certificate audit
hard_v8_eval_protocol.md              v8 agent-facing protocol
```
