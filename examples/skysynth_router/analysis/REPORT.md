# Static versus adaptive executable checks on the SkySynth router task — results

Protocol: `PROTOCOL.md` (frozen in the research checkout at `1383ecf`, launch order drawn
from that commit: static first). Runs 2026-09-20. One run per arm. Nothing below fed back
into code, selection or rerunning; the two endpoints were read once, in one batch, after
all selections were frozen by hash (the freeze tooling and file, run directories,
selected routers and endpoint results are in the archived research materials, not in
this repository). The arms were named `replication_v2_static` / `replication_v2_adaptive`
at the time; they are `configs/static` and `configs/adaptive` here.

## Runs

| | replication_v2_static | replication_v2_adaptive |
|---|---|---|
| launched (UTC) | 18:02 | 18:50 |
| attempts / valid | 24 / 24 | 24 / 21 |
| wall | 35 min (first→last attempt) | 44 min |
| spend | $60.07 (builders) | $89.71 ($84.01 builders + $5.69 proposer) |
| sessions, model | 24, all `claude-opus-4-8` | 31, all `claude-opus-4-8` |
| stop | max_real_attempts | max_real_attempts |
| distinct candidates eligible (fixed checks + OOF replay) | 24 of 24 | 22 of 24 |
| out-of-fold training U over eligible candidates: max / median / min | **0.4623** / 0.4516 / 0.3787 | 0.4364 / 0.4269 / 0.3903 |
| candidates dominating the generic on train-OOF: A / B / both | 7 / 0 / 0 | 3 / 1 / 0 |

Selection v2 (dedupe by sha, fixed checks + OOF replay, rank by OOF U, top five to validation,
max validation U):

| | selected | val U | val A q / $/req / late | val B q / $/req / late | 5 validation U |
|---|---|---:|---|---|---|
| static | `77cac27d` (captain-ahab) | **0.4550** | 0.5844 / 0.00796 / 0.026 | 0.3737 / 0.01025 / 0 | 0.4550, 0.4477, 0.4434, 0.4444, 0.4424 |
| adaptive | `565afb41` (captain-ahab) | 0.4313 | 0.5463 / 0.00565 / 0.025 | 0.3579 / 0.00981 / 0 | 0.4227, 0.4313, 0.4313, 0.4299, 0.4293 |

## Primary outcome: fresh OOD transfer endpoint

Label: *Fresh-family out-of-distribution generalization evaluation on previously unused
LLMRouterBench task families. A fresh OOD transfer endpoint: 81% of requests are MMLU-Pro,
no τ²-like workload; not a reproduction of the original benchmark distribution.*

| router | merged U | $/req | A q / $/req / late | B q / $/req / late | win predicate A | win predicate B |
|---|---:|---:|---|---|---|---|
| generic reference | 0.7608 | 0.00080 | 0.7787 / 0.00063 / 0.0150 | 0.7625 / 0.00102 / 0 | — | — |
| **replication_v2_static** | **0.7747** | 0.00076 | 0.7852 / 0.00068 / 0.0000 | 0.7660 / 0.00087 / 0 | q ✓ c ✗ (0.00068 vs 0.00063) late ✓ | **✓ ✓ ✓** (late equal at 0) |
| **replication_v2_adaptive** | **0.7748** | 0.00072 | 0.7852 / 0.00068 / 0.0000 | 0.7660 / 0.00077 / 0 | q ✓ c ✗ (0.00068 vs 0.00063) late ✓ | **✓ ✓ ✓** (late equal at 0) |

Static vs adaptive on the primary endpoint: **0.7747 vs 0.7748**, a difference of 0.0001. The
two selected routers make identical tenant-A choices on this endpoint (same q, cost and late)
and differ on B by $0.0001 per request. Both beat the generic by +0.014 and both satisfy the
full batch win predicate on this endpoint (with lateness equal at zero, reported as equality,
not strict improvement). Neither meets the interactive cost constraint, by $0.00005.

## Secondary outcome: original test (exploratory)

Label: *Exploratory in-domain benchmark result; the aggregate test endpoint had been opened
eight times before this protocol was frozen.*

| router | merged U | $/req | A q / $/req / late | B q / $/req / late |
|---|---:|---:|---|---|
| generic reference | 0.3927 | 0.00411 | 0.5317 / 0.00595 / 0.0537 | 0.3081 / 0.00167 / 0 |
| replication_v2_static | **0.4523** | 0.01001 | 0.5865 / 0.01024 / 0.0354 | 0.3909 / 0.00970 / 0 |
| replication_v2_adaptive | 0.4372 | 0.00787 | 0.5585 / 0.00667 / 0.0333 | 0.3752 / 0.00946 / 0 |
| (original static / adaptive, 2026-09-19) | 0.4217 / 0.4217 | | | |

Here the arms separate: static 0.4523 (the highest in-domain number any condition has
produced, exploratory) vs adaptive 0.4372, a gap of 0.015 in the opposite direction from the
perf_v1 pair (0.4428 vs 0.4404). Both exceed the original arms by 0.015–0.031. The win
predicate fails on cost for both tenants for both arms (as for every in-domain router so far).

## Mechanism record (adaptive arm)

| checkpoint (real attempts) | outcome | check | triggering artifact(s) |
|---|---|---|---|
| 8 | **published** bank-v2 | `evolved-ad625a676156facd` (`no_lost_request`): "Absolute rpm-reserve starves a serviceable low-tier provider, losing every request" | jack-sparrow `a481c25d` (fails: 4 lost + hang); reference passes twice; library mutant fails |
| 12 | **published** bank-v3 | `evolved-00edd61b2b56f95e` (`no_lost_request`): "Interactive router's absolute rpm-reserve (headroom_rpm=4) deadlocks every request on a rpm-limited provider" | captain-ahab `470277ca` and jack-sparrow `a481c25d` (fail: 6 lost + hang); reference passes; mutant fails |
| 16 | abstained | proposal "Requested model stranded by a full-horizon outage…" rejected: the reference pair does not pass it (admission rule working) | — |

Deliveries recorded (feedback written): 24, one per finalized attempt (captain-ahab 8,
captain-nemo 6, davy-jones 6, jack-sparrow 4). Visibility is not reading; delivery is not
understanding.

Do the artifacts pass the admitted checks? (owner-side replays of the two checks)

| artifact | check 1 (`…6156facd`) | check 2 (`…2b56f95e`) |
|---|---|---|
| trigger jack-sparrow `a481c25d` | FAIL (4 lost, hang) | FAIL (6 lost, hang) |
| trigger captain-ahab `470277ca` | pass | FAIL (6 lost, hang) |
| terminal captain-nemo `5430c2d4` | pass | pass |
| terminal davy-jones `2f7adc01` | pass | pass |
| terminal captain-ahab `b6c5b0b4` | pass | pass |
| terminal jack-sparrow `4f17cea7` | pass | pass |

Subsequent targeted commits (observed sequence, not attributed cause):

- jack-sparrow, whose `a481c25d` (19:03:36) triggered both checks, next committed `21042d76`
  at 19:17:29 "Concurrency-reserve coupling fix…" (invalid under bank-v3) and then `6c8ec3f6`
  at 19:32:43 "**Fix rpm-reserve deadlock** (INVALID→valid): bounded last-resort dispatch" —
  the mechanism check 2 names, 15 minutes after check 2's publication.
- captain-nemo `555bd59c` at 19:16:51: "harden against infinite-defer/**lost_request**. Both
  routers now force…" ten minutes after check 1 was delivered to it.
- captain-ahab, cited by check 2 via `470277ca` (19:06:23), was already at 0.4274 by
  19:27:59 with a "feasible/infeasible placement split"; all its later commits pass both.

Strategy convergence. The static arm's winner uses a fixed per-(tenant, task) model map
("the supplied predictor barely discriminates within a task, but the task-level signal is
strong"), the same shape as the perf_v1 winners. The adaptive arm's winner is per-prompt
pred-driven with a billed-cost penalty; its team spent the middle of the run on capacity
reservation and yielding (the two admitted checks are both about reserves deadlocking
requests), and its OOF training distribution is lower and narrower (median 0.4269 vs 0.4516).
Two arms, one run each: whether the checks steered the team toward correctness work at the
expense of model-choice work, or whether the teams simply diverged, cannot be separated here.

## What this experiment supports

- Under an honest training signal, a matched static control and adaptive checks produced
  routers that transfer equally to the fresh OOD endpoint (0.7747 vs 0.7748) and both improve
  on the generic there (+0.014) while satisfying the batch win predicate.
- On the original task (exploratory), the static arm's router scored higher (0.4523 vs
  0.4372); the adaptive arm's candidate distribution was lower throughout. This is one run per
  arm and the sign is opposite to perf_v1's pair (+0.002 adaptive over static); across the two
  pairs the checks effect is not distinguishable from zero.
- The mechanism worked as specified: two admitted checks from real candidate defects,
  triggering artifacts fail them, every terminal artifact passes them, one rejection by the
  reference rule, and named repairs after delivery. That is evidence the mechanism finds and
  propagates correctness defects, not evidence it raises utility.

Spend for this experiment: $149.78. Test endpoint openings now: 9 (this batch counted once).
