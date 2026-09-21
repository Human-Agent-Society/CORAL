# Evolving evaluation criteria

`coral.grader.evolution` lets a criteria-driven grader's rubric grow during a
run, in a way that is versioned, grounded in the artifacts agents actually
produced, admitted mechanically, and recorded well enough that a reader can
later tell which agent was exposed to which change. It exists to study one
question: does letting the evaluator learn from the trajectory change what a
team of agents builds, compared with an otherwise identical fixed evaluator?

## The cycle

```
attempt finalized ──► grade under current rubric version v
                        │
                        ├── checkpoint reached? (scored-observation clock: 8, 12, 16, ...)
                        │      no  → record a trigger decision; done
                        │      yes → stage evidence: recent feedback, artifacts, notes
                        │            proposer (claude -p, read-only, staged dir only)
                        │            ── proposals must QUOTE the evidence they rest on
                        │            admission filter (mechanical, see below)
                        │            publish v+1 (immutable) or record an abstention
                        │
                        └── event: scores bound to v; the manager records every later
                            prompt it dispatches, so exposure is a fact on disk
```

Three arms share one entry point (`EvolvingTaskGrader`, `evolution.mode`):

| arm | when the rubric may change | what the proposer sees |
|---|---|---|
| `static` | never | — |
| `adaptive` | at each configured checkpoint | task brief, recent evaluator feedback, staged artifacts, agents' notes |
| `yoked` | at the checkpoints its paired adaptive run published at, with the same criterion counts | task brief only |

The yoked arm is the control that separates "a plausible requirement can be
inferred from the task" from "artifact access contributed new information".
It is a study configuration, not a general-purpose feature; it lives here
because it is one `blind=True` switch on the same code path, which is what
makes the comparison fair.

## Why checkpoints

Earlier generations of this module fired the proposer from score statistics
(plateau, variance, "everyone passes"). Those measure how much the agent
population happens to vary, not whether the rubric still discriminates: on the
same task they fired at the earliest permitted attempt against a weak model and
missed the whole window against a strong one. Fixed checkpoints remove the
timing question so only the content question remains. `PolicyConfig.from_args`
refuses the old keys rather than ignoring them.

Checkpoints are indices on the **scored-observation clock**. A failed
evaluation (evaluator crash, timeout) is not an observation and does not advance
a checkpoint, so a proposer is never invoked because infrastructure failures
consumed its evidence window. Submissions and failures are counted and written
on every record separately; the yoked arm replays the same scored indices.
`latest_publication_attempt` alone is a bound on the real-attempt clock, since it
protects exposure, which is a matter of attempts left in the budget.

## Admission is mechanical

A proposal is published only if all of these hold (`proposals.filter_proposals`):

1. it names a source that was actually shown and quotes text that appears in it
   verbatim (whitespace/case-insensitive) — the grounding gate;
2. it is not a duplicate of an anchor, an active criterion, or anything ever
   admitted (normalized name);
3. the proposer declared it feasible for the agents, gave a task-level
   rationale, and declared that it applies across different solution strategies;
4. a slot is free under `max_criteria`, at most `max_new_criteria_per_round`.

Agent-authored files are staged so the proposer can read them, but they are
not quotable sources: a sentence planted in an artifact cannot satisfy the
grounding gate. `injection_scan.py` reports, after the run, any agent text that
looks aimed at the proposer.

Nothing judges whether an admitted criterion is *warranted*. That is analysis
work done by a person afterwards on a handful of criteria; making it runtime
machinery would put a second model in the loop that the study cannot audit.

## What is written down

Under `.coral/private/evolving/` (agents cannot read it):

- `versions/v<N>.json` — immutable rubric versions with per-criterion
  provenance: cited source, the quote that passed the gate, source attempts and
  notes, the attempt and agent whose evidence triggered the version;
- `events/<attempt>.json` — one per graded attempt: scores, the version scored
  under, failures, criteria in force;
- `trigger_decisions.jsonl` — one record per grade: checkpoint index and value,
  gate blockers, window, and for a checkpoint that ran, `published` /
  `abstained` / `blocked` (the proposer was never invoked: deadline or cap —
  not the same claim as an abstention, and never replayed by a yoke as one);
- `proposer_contexts/` — the exact bytes each proposer call was shown;
- `rejected.jsonl`, `RUBRIC_CHANGELOG.md`, and `.coral/private/run_manifest.json`
  (the arm, written once, never rewritten).

And in `.coral/private/research/intervention_events.jsonl`
(`coral.hub.interventions`), one event per prompt the manager dispatched to an
agent's runtime, with the rubric version in force. "Dispatched" means the runtime
process was started with that prompt; it says nothing about whether the provider
accepted it, whether it entered the model's context, or whether the agent read or
acted on it.

## Correctness properties the tests pin

- A score is bound to the version it was scored under, even when another grade
  publishes a new version while it is in flight (`test_evolution_integration`).
- A pending or failed attempt is never an observation and never advances a
  checkpoint; finalization is monotonic and claimed by exactly one grader
  (`test_evolution_protocol`, `test_grader_daemon`).
- The attempt cap is enforced at submission, under a lock, so a 24-attempt
  budget yields exactly 24 committed attempts (`test_hooks`).
- The blind prompt contains only the brief and the rubric; the yoked proposer
  reads nothing from the run directory; an exported schedule carries checkpoint
  indices, outcomes and counts, never criterion text, and rejects edits by hash.
- A proposal whose quote is not in its cited source is rejected; agent-authored
  sources are readable but never quotable.

## Using it

```python
from coral.grader.evolution import EvolvingTaskGrader

class EvolvingMyGrader(EvolvingTaskGrader):
    inner_grader_cls = MyGrader   # any TaskGrader that scores args["criteria"]
```

```yaml
grader:
  entrypoint: my_pkg.evolving:EvolvingMyGrader
  hide_args: true                # keep the arm and the rubric out of agents' reach
  args:
    criteria: [...]              # seed rubric
    evolution:
      mode: adaptive             # static | adaptive | yoked
      checkpoints: [8, 12, 16]   # scored-observation indices
      max_criteria: 11
      latest_publication_attempt: 19
      window: 3
      max_new_criteria_per_round: 2
      proposer_model: claude-opus-5
```

`examples/evolving-rubric-demo/` runs the whole cycle offline with a scripted
proposer (`evolution.proposer_command`), so the mechanism can be read end to end
in a few minutes without a model call.
