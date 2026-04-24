# Japan Elderly Market Analysis 2050 — RACE Evaluation Task

## Origin

Adapted from DeepResearch Bench (https://arxiv.org/abs/2506.11763), Task ID 51.
Uses the RACE (Reference-based Adaptive Criteria-driven Evaluation) framework.

- **Domain**: Finance & Business
- **Language**: English
- **Difficulty**: PhD-level deep research task

## Task

The agent must produce a comprehensive market size analysis report for Japan's
elderly demographic from 2020 to 2050, covering population projections, consumption
potential (clothing, food, housing, transportation), consumer willingness, and
changing consumption habits.

## RACE Evaluation

Unlike binary rubric evaluation, RACE scores the agent's output on a **continuous
0-10 scale** across **4 dimensions** with **25 total criteria**:

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| Comprehensiveness | 0.30 | 7 criteria |
| Insight | 0.33 | 5 criteria |
| Instruction Following | 0.22 | 5 criteria |
| Readability | 0.15 | 8 criteria |

The agent's report is scored **comparatively** against a reference article by
an LLM judge. The final score is `target / (target + reference)`:
- 0.5 = equal to reference
- \>0.5 = outperforms reference
- <0.5 = underperforms reference

## Data Isolation

The reference article ships inside the grader package at
[`grader/src/race_japan_grader/references/reference_article.md`](grader/src/race_japan_grader/references/reference_article.md)
— it's installed into the grader's isolated venv by `grader.setup` and loaded
by the judge via `importlib`-style package-local resolution. The agent
**cannot access** the reference: the grader venv is outside the agent
worktree and the file is never copied into the agent's workspace.

## Grader

The grader ships as a standalone Python package under [`grader/`](grader/) and
is wired into each task.yaml via:

```yaml
grader:
  entrypoint: "race_japan_grader.grader:Grader"
  setup:
    - "uv pip install -e ./grader"
```

CORAL creates an isolated venv at `.coral/private/grader_venv/` at launch time
and runs the setup commands there, so the grader's heavy deps (OpenAI client,
etc.) never leak into the agent workspace.

## How to Run

```bash
# Condition E — rubric-guided. Agent sees all 25 criteria in CORAL.md.
coral start -c examples/race-japan-elderly/task.yaml

# Condition A — baseline. Same grader + rubrics, but the rubrics live under
# grader.args.rubrics and are NOT surfaced to the agent.
coral start -c examples/race-japan-elderly/task_baseline.yaml

# Aggregate-only feedback — agent sees dimension scores but not per-criterion detail.
coral start -c examples/race-japan-elderly/task_aggregate_only.yaml

# Agent judge — 1st-party apex_judge grader with auto-evolving rubrics (no reference article).
coral start -c examples/race-japan-elderly/task_agent_judge.yaml
```

## Files

```
examples/race-japan-elderly/
├── README.md
├── task.yaml                           # Condition E (rubric-guided)
├── task_baseline.yaml                  # Condition A (rubrics hidden)
├── task_aggregate_only.yaml            # Dimension-level feedback only
├── task_agent_judge.yaml               # Dynamic rubric via apex_judge
├── grader/                             # race_japan_grader package
│   ├── pyproject.toml
│   └── src/race_japan_grader/
│       ├── grader.py
│       └── references/
│           └── reference_article.md    # Reference article (shipped in wheel,
│                                       # loaded by judge; agent never sees it)
└── repo/
    └── report.md                       # Placeholder — agent overwrites
```
