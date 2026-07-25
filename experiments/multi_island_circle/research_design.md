# Circle Packing topology threshold study

## Purpose and interpretation boundary

The NK studies isolate search geometry but expose only bit strings and scalar
feedback.  This study uses the existing N=26 Circle Packing task as a separate
real-code robustness test.  Agents can develop materially different algorithm
families, implementation tricks, and valid packings, so a migrant can carry a
tested artifact rather than a synthetic certificate or a local bit mutation.

Circle Packing is still an optimization benchmark, not a complete proxy for
software engineering or research collaboration.  A positive result therefore
supports a multi-basin real-artifact search claim; it does not establish that
multi-island is universally useful or that migration improves every semantic
task.

## Frozen design

Four `mafia/glm-5.2` OpenCode agents use the same seed program, role protocol,
model-API-only network allowlist, SRT sandbox, and equal per-agent quotas.
Conditions are:

| condition | shared scopes | migration |
| --- | ---: | --- |
| global | 1 | disabled |
| partition | 2 | disabled |
| multi-island | 2 | enabled, two balanced round-robin moves at most per cycle |

The registered budgets are 32, 64, and 128 real evaluations.  Migration cadence
is fixed at every 16 realized real evaluations, rather than rescaled per budget,
so the ladder varies the number of post-migration opportunities: approximately
one, three, and seven checks before the stop boundary.  Each agent receives
exactly one quarter of the total budget.  Eight stochastic repetition blocks
are required for a confirmatory threshold; condition launch order rotates as a
Latin square to balance sequential API drift.

The existing grader benchmark is public and deterministic.  The experiment
adds an inner 600-second candidate deadline and a 660-second outer grader
deadline so candidate timeouts consume a real attempt instead of racing into a
free grader-infrastructure error.  Tune mode is rejected before scoring.
Candidate Python runs in a no-network bubblewrap namespace exposing only its
read-only checkout, temporary storage, and the NumPy/SciPy runtime; prior
results, host paths, and grader state are not mounted.  The analyzer retains a
second source-level audit for forbidden network or CORAL-private access.
Before launch, the runner also fails closed unless the shared multi-island SRT
contract scopes state and worktree visibility to the current island. The
analyzer rejects runtime traces containing raw Git inspection or explicit
foreign-island state/worktree access. Run
`python experiments/multi_island/sandbox_canary.py` once on the active build
before the B=32 smoke test to exercise the boundary with a real `coral eval`.

## Outcomes

Primary performance is final best valid normalized score.  Best-so-far AUC,
gain over the frozen seed score, time to best, null/timeout rate, and score
range are secondary performance measures.  The analysis also reports:

* latest-source structural diversity across agents;
* duplicate and near-reused source trajectories;
* observed algorithm-family labels, used only as diagnostics;
* realized migration counts and ticks;
* post-migration attempts, source continuity, and improvements over the
  destination frontier that existed at arrival.

Source similarity and keyword labels are imperfect behavioral diagnostics and
never substitute for performance.  A multi-island cell must contain a real
migration followed by a real submission; otherwise it cannot identify transfer.

## Registered decision rule and staging

The primary causal contrast is `multi_island - partition`, because partition
holds the two knowledge boundaries fixed and removes migration.  The secondary
contrast is `multi_island - global`.  The earliest supported threshold is the
first registered budget at which all of the following hold:

1. all eight repetition blocks pass integrity checks for all three conditions;
2. mean paired score improvement is at least 0.01 over both partition and
   global;
3. both paired bootstrap 95% lower bounds are above zero;
4. every multi-island cell has a real migration and a later real submission.

Run one B=32 repetition as an operational smoke test.  Advance to the full B=32
block only if all cells meet budget/quota gates and the multi-island cell has
post-migration work.  Advance to B=64 and B=128 regardless of the direction of
the lower valid result, but never tune budgets, cadence, or strategy prompts to
make multi-island win.  All lower-budget and failed operational cells remain
reported.  The modular certificate task is analyzed separately as a mechanism
positive control and cannot rescue a null or negative Circle Packing result.
