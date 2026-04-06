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

The reference article is stored in `eval/reference_article.md` and copied to
`.coral/private/` at runtime via `grader.private`. The agent **cannot access**
the reference — only the grader process reads it from `.coral/private/`.

## How to Run

```bash
# Condition E (rubric-guided — agent sees 25 criteria across 4 dimensions)
coral start -c examples/race-japan-elderly/task.yaml

# Condition A (baseline — agent doesn't see criteria)
coral start -c examples/race-japan-elderly/task_baseline.yaml
```

## Files

```
examples/race-japan-elderly/
├── README.md
├── task.yaml                           # Condition E
├── task_baseline.yaml                  # Condition A
├── eval/
│   └── reference_article.md            # Reference article (hidden from agents)
└── repo/
    └── report.md                       # Placeholder — agent overwrites
```
