# High-dimensional multi-island difficulty ladder

The original `N=20` Smooth/Rugged NK cells are retained as sanity checks. They
are not sufficient to establish a ruggedness threshold: `K=0` is separable,
`K=4` has many local optima but only 16 scalar queries are available, and each
condition used one frozen landscape seed.

This follow-up fixes the main design limitation with a pre-registered ladder:

| task | N | K | role |
| --- | ---: | ---: | --- |
| `smooth128` | 128 | 0 | high-dimensional separable control |
| `rugged128_k4` | 128 | 4 | moderate epistasis |
| `rugged128_k12` | 128 | 12 | strong epistasis |
| `rugged128_k24` | 128 | 24 | strongest ladder stress test |

Each task has global, partition, and multi-island conditions, three
operational repetitions, four `mafia/glm-5.2` OpenCode agents, and exactly 24
finalized real evaluations. Migration checks every six evaluations. The
hard-ladder-specific role seed explicitly names the 24-evaluation budget.

There is no exact oracle at `N=128`. `diagnose_landscapes.py` records a fixed
operator-side Monte Carlo and multi-start greedy reference, plus random
baseline moments. `analyze_hard.py` reports raw score, fraction of the declared
reference gain, random-z score, best-so-far AUC, diversity, migration
compliance, null-rate, and agent-runtime/API error counts. The reference is
approximate and is never called a global optimum.

Validate and inspect the matrix without launching agents:

```bash
uv run coral validate experiments/multi_island_hard/tasks/institutional_landscape
uv run python experiments/multi_island_hard/run_matrix.py --dry-run
```

Run and analyze:

```bash
uv run python experiments/multi_island_hard/run_matrix.py \
  --results-root /var/tmp/coral-institutions-results/hard-ladder-v1 \
  --max-parallel 2
uv run python experiments/multi_island_hard/analyze_hard.py \
  --results-root /var/tmp/coral-institutions-results/hard-ladder-v1
```

Results from the first launch that accidentally used the pilot 16-evaluation
role protocol are marked `experiment-invalid.json` and are not analyzed.
The next partial launch showed agents spending their search on false-positive
seed reconstruction from rounded scalar scores. It is also invalidated; the
final protocol states that the seed is an independently sampled 256-bit token
and treats the task as black-box search.

The manager's stop condition is audited rather than trusted: because agents
can submit concurrently, a run may finalize one extra real attempt before the
manager observes the stop threshold. Any cell whose finalized real count is
not exactly 24 is invalid for the ladder. The interrupted July 24 collection
was not used as a result set for this reason (one cell reached 25 real
attempts).
