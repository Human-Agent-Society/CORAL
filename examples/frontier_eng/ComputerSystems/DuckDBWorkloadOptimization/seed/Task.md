# DuckDB Workload Optimization Task

## Background

In practical analytics systems, the same machine often serves multiple heavy SQL workloads with joins, aggregations, and window functions. Real performance depends on both:

- physical design choices (indexes / precomputed tables), and
- query-shape choices (semantics-preserving rewrites).

This task evaluates whether an agent can optimize these two levers jointly while preserving correctness.

## Engineering Value

Improving workload runtime without changing business semantics directly reduces compute cost and latency for dashboards, ad-hoc analysis, and periodic reporting jobs.

## Official Data & Query Source

All workload SQL and data setup are sourced from official DuckDB benchmark files:

- Repo: `https://github.com/duckdb/duckdb`
- Commit: `ff4f70eeee83cfd3dae6577fc9b2b448d5fbdb35`

Imported source files include:

- `benchmark/tpch/sf1/load.sql`
- `benchmark/tpch_plan_cost/queries/q03.sql`
- `benchmark/tpch_plan_cost/queries/q05.sql`
- `benchmark/tpch_plan_cost/queries/q07.sql`
- `benchmark/tpch_plan_cost/queries/q10.sql`
- `benchmark/tpch_plan_cost/queries/q12.sql`
- `benchmark/tpch_plan_cost/queries/q18.sql`
- `benchmark/micro/window/window_partition.benchmark`

These files are copied under `references/duckdb_official/` and mapped by `references/problem_config.json`.

## Objective

Given one candidate program (`scripts/init.py`), output optimization decisions for two sub-problems:

1. **Index / MV selection**
   - Propose optional `CREATE INDEX ...` and optional `CREATE TABLE/CREATE MATERIALIZED VIEW ... AS SELECT ...` statements.
2. **Query rewrite**
   - For selected query IDs, provide rewritten SQL that is semantically equivalent to the official baseline SQL.

## Submission Contract

Your candidate program must expose:

```python
def solve(problem: dict) -> dict:
    ...
```

and return a JSON-serializable dict with fields:

- `benchmark_id: str`
- `index_statements: list[str]`
- `materialized_view_statements: list[str]`
- `query_rewrites: dict[str, str]`

### Limits

From `problem_config.json`:

- `max_indexes = 12`
- `max_materialized_views = 4`
- `max_rewrites = 3`
- `max_sql_chars = 12000` (per SQL statement)

### SQL Safety Rules

- Rewrite SQL must be a single read-only `SELECT`/`WITH` query.
- Index SQL must follow `CREATE INDEX ... ON table(col, ...)` and reference existing base-table columns.
- Materialized-view SQL must follow `CREATE TABLE/CREATE MATERIALIZED VIEW mv_* AS SELECT ...`.

## Evaluation Procedure

The evaluator (`verification/evaluator.py`) runs the following steps:

1. Build base database from official scripts:
   - TPCH SF1 load (`CALL dbgen(sf=1)` from official `load.sql`)
   - official micro-window load section (`window_partition.benchmark`, `load` section)
2. Run baseline program and candidate program to get two submissions.
3. Validate submission format and SQL safety constraints.
4. **Index/MV track**:
   - Apply physical statements.
   - Execute index workload queries and measure median runtime per query.
   - Track total cost = setup time + query runtime.
5. **Rewrite track**:
   - For each rewrite workload query, execute baseline SQL and candidate SQL.
   - Check exact result equivalence (normalized canonical compare).
   - Measure baseline/candidate runtime totals.
6. Aggregate metrics.

## Scoring

Let:

- `index_speedup = index_baseline_total_s / index_candidate_total_s`
- `rewrite_speedup = rewrite_baseline_total_s / rewrite_candidate_total_s`
- `rewrite_semantics_valid ∈ {0,1}`

Final score:

- if `rewrite_semantics_valid == 1`:
  - `combined_score = 0.5 * index_speedup + 0.5 * rewrite_speedup`
  - `valid = 1.0`
- else:
  - `combined_score = 0.0`
  - `valid = 0.0`

## Failure Cases

Score is forced to zero if any of the following occurs:

- Candidate program cannot run.
- Submission format is invalid.
- SQL violates safety/limit constraints.
- Rewrite results are not semantically equivalent.
- Evaluator timeout or runtime error.

## Required Local Tests

From task directory:

```bash
python verification/evaluator.py scripts/init.py
```

From repository root:

```bash
python -m frontier_eval task=duckdb_workload_optimization algorithm.iterations=0
```
