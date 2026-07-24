# Multi-island institutional experiment

This directory contains the pre-specified experiment behind
`blog/agents-need-institutions.html`.  It tests the claim that a useful agent
institution needs both boundaries (islands) and selective exchange
(migration), rather than simply adding more agents to one shared pool.

## Frozen design

All cells use four OpenCode agents running `mafia/glm-5.2`, OS-level SRT
sandboxing, `agents.research=false`, the same prompts, and a global budget of
16 finalized real evaluations.  Each cell has three independent repetitions.
Repetitions are operational replicates: the task landscape is held fixed while
agent sampling and scheduling vary.

Tune mode is disabled in the experiment configs and the seeded role protocol:
all useful fitness queries must consume the same 16-evaluation real budget.

The four topologies are:

| Name | Islands | Migration | Interpretation |
|---|---:|---:|---|
| `global` | 1 | off | One fully shared institution |
| `partition` | 2 | off | Boundaries without exchange |
| `multi_island` | 2 | on | Boundaries plus selective exchange |
| `independent` | 4 | off | Four isolated individual searches |

Migration checks whenever the run crosses another 6-global-real-evaluation
boundary, ranks on the most recent 6, permits candidates after one real
evaluation, moves at most two agents per cycle, and applies a 6-evaluation
remigration cooldown. Because the manager polls asynchronously, several fast
grades can finalize between checks; the realized application tick can therefore
land just after the nominal boundary and is recorded from arrival-note timing.

The primary topology contrasts are intent-to-treat: a `multi_island` run stays
in its assigned cell even if a cycle finds no eligible balanced swap. Arrival
notes and their realized eval counts are audited as treatment-compliance data;
excluding zero-migration outcomes would condition on post-assignment search
results.

The exact matrix is:

| Task | Global | Partition | Multi-island | Independent | Runs |
|---|---:|---:|---:|---:|---:|
| Kernel Builder (real benchmark) | 3 | 3 | 3 | 3 | 12 |
| Smooth NK (`N=20, K=0`) | 3 | 3 | 3 | — | 9 |
| Rugged NK (`N=20, K=4`) | 3 | 3 | 3 | — | 9 |
| **Total** | | | | | **30 runs / 480 real evals** |

`partition` is the migration ablation with the same two-island boundary as
`multi_island`. `independent` is included on the real task to distinguish the
benefit of collaboration from mere parallel random search. It is omitted from
the controlled interaction because `global` and `partition` already identify
the boundary effect while `partition` and `multi_island` identify migration.

## Hypotheses and metrics

1. `partition` and `multi_island` retain greater solution diversity than
   `global`, measured as mean pairwise distance between each agent's latest
   evaluated solution at evaluation 8 and 16.
2. `multi_island` outperforms `partition` on final best score and best-so-far
   AUC: migration should transfer discoveries that isolated islands cannot.
3. The performance advantage of `multi_island` over `global` is larger on the
   rugged (`K=4`) landscape than on the smooth (`K=0`) landscape.
4. On Kernel Builder, `multi_island` beats both `global` and `independent` in
   final cycle count or exposes an honest null/negative result.

Primary performance is the best finalized real score after 16 evaluations.
Secondary performance is normalized best-so-far AUC. Controlled-task diversity
is normalized Hamming distance; Kernel Builder diversity is 1 minus Jaccard
similarity over Python-token 5-grams. The report shows all run-level points,
means, and 95% replicate-bootstrap intervals. With only three repetitions,
intervals are descriptive rather than a claim of high-powered significance.

A task-level failure (for example, an incorrect kernel with `score: null`) is a
legitimate real search attempt: it consumes budget and leaves best-so-far
unchanged. Only records explicitly classified as `grader_error` indicate
infrastructure failure and are audited separately.

The disabled-tune gate can still receive an attempted `--tune` submission. A
rejected call returns no score and only the fixed "Tune mode is disabled"
message; it is counted in the audit but does not invalidate a run. Any tune
record that returns a score or bypasses that gate is a protocol violation and
is excluded.

Before the authoritative controlled matrix, two global cells exposed an
experiment-design threat: their initial human-readable hidden seeds were
potentially guessable from scalar fitness probes. Those cells are retained as
excluded pilots with an `experiment-invalid.json` marker and are not analyzed.
The authoritative `K=0` and `K=4` instances instead use independently sampled
256-bit random seeds, frozen before the remaining controlled runs. An
exhaustive pass over all 1,048,576 candidates confirms one one-bit local
maximum for `K=0` and 626 for `K=4`; the full operator-side output is frozen in
`landscape_diagnostics.json`. Candidates and seeds are never placed in an
agent worktree. The seeds are published here only after data collection for
auditability; a new blind replication should rotate them (or disable network
access to any public copy).

One initial Kernel `partition` cell exposed a separate timeout-classification
race: the candidate and outer grader both had 120-second deadlines, so a slow
candidate was labeled `grader_error` before the grader could return a normal
null-score task failure. That cell is also retained with an
`experiment-invalid.json` marker. Authoritative retries preserve the
candidate's 120-second limit while giving the outer grader 30 seconds of
reporting grace.

No cell will be silently dropped. Failed or incomplete runs remain in
`manifest.json`; they are retried into a new suffixed directory and both the
failure and retry are retained. Analysis accepts only runs with at least 16
finalized real attempts, rejects any explicitly invalidated pilot, and records
any overshoot.

## Commands

Validate the controlled grader first:

```bash
uv run coral validate experiments/multi_island/tasks/institutional_landscape
```

Reproduce the exhaustive landscape diagnostics (NumPy is operator tooling,
not a task or grader dependency):

```bash
uv run --with numpy python experiments/multi_island/diagnose_landscapes.py
```

Show the frozen commands without launching agents:

```bash
uv run python experiments/multi_island/run_matrix.py --dry-run
```

Run the matrix (results must remain outside `$HOME` for SRT write precedence):

```bash
uv run python experiments/multi_island/run_matrix.py \
  --results-root /var/tmp/coral-institutions-results/matrix \
  --max-parallel 2
```

Generate CSV summaries and SVG figures:

```bash
uv run python experiments/multi_island/analyze.py \
  --results-root /var/tmp/coral-institutions-results/matrix
```

The analysis writes run-, attempt-, summary-, and direct-contrast CSVs. The
contrast table includes multi-island minus each ablation plus the pre-specified
smooth-versus-rugged difference-in-differences. Bootstrap intervals resample
the three operational repetitions and are descriptive.

`run_matrix.py` interleaves tasks and conditions within each repetition to
reduce time/provider drift and writes an operator log plus a machine-readable
manifest for every launch.
