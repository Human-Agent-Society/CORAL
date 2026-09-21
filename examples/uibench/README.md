# UI-Bench three-arm co-evolution study

Does letting the evaluator learn from the trajectory change what a team of
agents builds, compared with an otherwise identical fixed evaluator? This
directory holds the study that first asked that question with
`coral.grader.evolution`: the generated run configurations for two frontend
tasks under three arms, the yoke schedules that bind the control arm to the
treatment arm, the analysis tooling, and a curated evidence set from the six
completed runs.

The headline finding is a single completed co-evolution loop, written up in
[`CASE_STUDY.md`](CASE_STUDY.md): the adaptive proposer read three artifacts,
found that the page with the *highest* interaction score was the one a keyboard
user could not operate, published a criterion saying so, and within twelve
minutes all four agents (including one whose page the proposer had never seen)
had committed targeted keyboard changes; two of those were independently
browser-verified. That is a mechanism demonstration. It is not a quality result, and the study does not
claim one; see "What is and is not claimed" below.

## The design

Three arms, one grader class, one seed rubric, one budget of 24 real attempts
per run with four Sonnet agents:

| arm | rubric | proposer sees |
|---|---|---|
| **static** | the five seed criteria for the whole run | never invoked |
| **adaptive** | may grow at scored-attempt checkpoints 8, 12, 16 (at most two criteria each, cap 11) | the last three scored attempts: evaluator feedback, staged artifacts, agents' notes |
| **yoked** | grows at exactly the checkpoints, and by exactly the counts, its paired adaptive run published at | the task brief and the current rubric only |

The yoked arm separates "a plausible requirement can be inferred from the
task" from "artifact access contributed new information". Both evolving arms
use the same proposer model (Opus), the same proposal schema, the same
grounding gate and the same admission filter; the yoked proposer simply has no
trajectory to quote from. Its schedule is exported from the adaptive run
(`schedules/*.json`, hash-bound) so a yoked config cannot drift from its twin.

Two tasks were run, chosen to differ in how much the brief specifies:

- **fellowship** — UI-Bench task 6, a fellowship intake portal with eleven
  mandated screens and behaviours (`fellowship_*`);
- **museum** — an open brief for a Rotterdam contemporary-art museum site,
  four lines long, mandating nothing (`museum_*`, brief in `briefs/museum.txt`).

## Files

| path | what it is |
|---|---|
| `make_task.py` | The only way a config is written. The `task:` block is a pure function of the UI-Bench row; the arm touches only `grader.args.evolution`, and `hide_args: true` keeps that block out of the config agents can read. |
| `.cache/` (ignored) | Where `make_task.py` caches the UI-Bench prompt table after fetching it from the pinned dataset revision and verifying its sha256. The table itself is not committed; see "Provenance" below. |
| `briefs/` | Brief overrides; `museum.txt` is the open-ended task. |
| `{museum,fellowship}_{static,adaptive,yoked}/task.yaml` | The six generated configs of record. Regenerate, never edit: `tests/test_uibench_study.py` fails if a committed config differs from what the generator emits. |
| `schedules/` | Yoke schedules exported from the two adaptive runs: checkpoints `[8, 12, 16]`, accepted counts `[2, 2, 2]`, all three checkpoints published. |
| `analysis/` | The scripts that build the ledger and tables from run directories, plus the curated evidence set needed to check the case study. See [`analysis/README.md`](analysis/README.md). |
| `CASE_STUDY.md` | The keyboard-operability chain and its yoked contrast. |

The grader is `examples/frontend-eval` (a Playwright-driving evaluator agent);
`EvolvingAgenticEvaluator` there is a two-line subclass naming it as the inner
grader for `coral.grader.evolution`.

## Running an arm

```bash
# regenerate a config (all six are committed; this is how they were made)
cd examples/uibench
python make_task.py --id 6 --arm adaptive --model claude-sonnet-4-5 --attempts 24 --name fellowship_adaptive

# run it
uv run coral start -c examples/uibench/fellowship_adaptive/task.yaml

# after an adaptive run finishes, export its schedule for the yoked twin
uv run python -m coral.grader.evolution.schedule results/<task>/<run> > examples/uibench/schedules/fellowship_adaptive_r2.json
python make_task.py --id 6 --arm yoked --model claude-sonnet-4-5 --attempts 24 \
    --schedule ../schedules/fellowship_adaptive_r2.json --name fellowship_yoked
```

A yoked config must be generated *after* its adaptive twin has run; the
schedule file is what makes it a control for that specific run. Requirements
are those of `examples/frontend-eval` (Node for the Playwright MCP server, a
`claude` CLI, an API key or gateway). A full run of one arm costs on the order
of a few hundred evaluator and agent turns per attempt and is not cheap.

## What is and is not claimed

**Claimed, and reproducible from the evidence set:**

- The mechanism worked as specified in both adaptive runs: three checkpoints,
  two grounded criteria admitted at each, every criterion carrying the quote
  that passed the grounding gate, a version-bound score for every attempt.
- Adaptive criteria were artifact-diagnostic where yoked criteria were not.
  A single unblinded coder rated 10 of 12 adaptive criteria as locating a
  specific defect in a named artifact and 0 of 10 yoked criteria as doing so;
  9 of 10 yoked criteria substantially overlapped or near-duplicated a seed
  criterion (`analysis/evidence/annotations.json`, rules stated first, basis
  per judgement).
- Agents responded to published criteria. Eleven commits across the 22
  criteria name the criterion they target; for the keyboard case every agent
  made a targeted change within twelve minutes, and two of the four repairs
  were independently browser-verified.

**Provisional, and stated as such wherever it appears:**

- The external quality comparison. A blind Opus judge asked the UI-Bench
  pairwise question preferred adaptive over static 8:6 on museum and 10:3 on
  fellowship (16 pairs each, order-unstable pairs excluded). Two things keep
  this from being a result: one run per cell, and the museum yoked arm is a
  complete yoke for only two of three publications (its third checkpoint
  abstained where two criteria were required, which voids that pair under the
  study's own rule). The judge framework, its frozen prompts and its outputs
  are research material and are not part of this PR; they live with the
  archived run directories. The numbers are quoted here only with that
  caveat attached.

**Not claimed:**

- That rubric evolution *caused* the repairs rather than equivalent feedback
  delivered some other way. The static arm received no such feedback, so the
  design cannot separate "the evaluator scored this" from "someone said this".
- Anything about tasks other than these two, or about agents other than Sonnet.

## Protocol note

The six runs of record were made under **protocol 1** of the evolution
module: checkpoints were counted on the real-attempt clock rather than the
scored-observation clock the shipped module uses, and the agent-facing status
label (`improved` / `regressed`) compared a score against the agent's best
across *all* rubric versions, so adding a criterion could report unchanged
work to the agent as a regression. Neither affects the mechanical record
(versions, quotes, events, commits) that the evidence set is built from, but
new runs under the shipped module belong in their own manifest and must not
be pooled with these (`analysis/runs_manifest.json` says so in its header).
The configs in this directory are regenerated for the shipped schema and
differ from the historical ones only inside `grader.args.evolution` comments
and in the removal of keys the module no longer accepts.

The full raw record of the six runs (run directories, proposer contexts,
Playwright traces, behaviour-check results, judge transcripts) is too large
for this repository and is archived separately; everything in
`analysis/evidence/` is derived from it by the scripts in `analysis/` and
names the run it came from.

## Provenance of the prompt table

The task briefs come from `UI-Bench Prompts - Main.csv` in the Hugging Face
dataset `AfterQuery/ui-bench` at revision
`3a8ec80d04b1498fbf12d275bbc5717413841015`, the 30-brief synthetic prompt set
of the UI-Bench benchmark (arXiv:2508.20410). The dataset card at that
revision declares no license, so the table is **not redistributed** in this
repository. `make_task.py` fetches it from that exact revision on first use,
refuses it unless its sha256 is
`a36f5e1ac51c5d8cb72f33fe78df539babb5a8976f906b0cdc96cd896361c51d`, and caches
it under the ignored `.cache/` directory; every generated config records the
repository, file, revision and digest in its header. The six committed configs
embed the one brief the study used (UI-Bench 6) and stand on their own; the
fetch is needed only to regenerate them or to build a config for another task.
Tests that regenerate configs skip when the table cannot be fetched.
