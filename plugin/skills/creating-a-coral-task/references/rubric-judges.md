# Rubric-judge graders (scoring open-ended outputs)

When success isn't a number your code can compute — a report, a memo, a legal analysis, a design doc — let an LLM judge the artifact against a rubric. CORAL ships two reusable judge graders as example packages. You don't write the grader; you point `grader.entrypoint` at the packaged judge and supply the rubric in `grader.args`.

Both subclass `TaskGrader` and return a `ScoreBundle` with one `Score` per criterion plus a weighted `aggregated`. Both run a sub-agent (`runtime` + `judge_model`) to read the artifact and apply the rubric, so the agent worktree must produce the named file(s).

## When to reach for a judge vs. a code grader

- The thing you care about is **quality of prose/structure/argument**, not a measurable quantity → judge.
- You *can* compute the number (accuracy, speedup, pass-rate) → code grader, every time. Judges are slower, cost LLM calls per eval, and are noisier. Don't judge what you can measure.

## Option A — static rubric (you define the criteria)

`StrictRubricJudgeGrader` — example at `examples/race-japan-elderly/`. You write the criteria up front; the judge applies the same rubric every eval. Deterministic, auditable, the default choice.

```yaml
grader:
  entrypoint: "race_japan_grader.grader:Grader"
  setup:
    - "uv pip install -e ./grader"
  timeout: 600
  direction: maximize
  args:
    files: ["report.md"]              # artifact(s) the agent must produce
    runtime: claude_code              # runtime used to run the judge
    judge_model: opus
    judge_max_turns: 30
    reference_files: ["reference_article.md"]   # optional gold reference the judge compares against
    feedback_level: full              # full | aggregate_only | score_only
    rubrics:
      - name: "Accuracy"
        description: "Every factual claim is supported by the source material."
        weight: 2.0
      - name: "Coverage"
        description: "Addresses all required sections of the brief."
        weight: 1.0
      - name: "Clarity"
        description: "Reads clearly for the target audience; no jargon left unexplained."
        weight: 1.0
```

Each criterion scores 1.0 (PASS) or 0.0 (FAIL); `aggregated` is the weight-normalized pass fraction. `feedback_level` controls how much the agent sees:
- `full` — per-criterion verdicts + rationale (best for steering agents)
- `aggregate_only` — just the overall score + summary
- `score_only` — bare number (use when detailed feedback would let agents overfit the judge)

## Option B — dynamic rubric (the judge invents + evolves criteria)

`AgentJudgeGrader` — example at `examples/apex-eggshell-skull/`. The judge generates a rubric on the first eval and evolves it as agents plateau — useful for genuinely open-ended tasks where you can't enumerate the criteria up front.

```yaml
grader:
  entrypoint: "apex_judge.grader:Grader"
  setup:
    - "uv pip install -e ./grader"
  timeout: 600
  direction: maximize
  args:
    files: ["memorandum.docx"]
    model: opus
    runtime: claude_code
    judge_max_turns: 30
    dynamic_rubric: true
    min_criteria: 3
    max_criteria: 15
```

Trade-off: more adaptive, but the moving target makes scores across evals less directly comparable and harder to audit. Prefer the static rubric unless you genuinely can't pin the criteria down.

## Practical notes

- **Make the artifact filename a hard contract** in `task.description` — the judge grades exactly `files: [...]`; if the agent writes `final_report.md` and you asked for `report.md`, every eval fails.
- **Judges cost an LLM call (or many) per eval.** Keep `agents.count` modest and `grader.parallel.max_workers: 1` unless you've confirmed the judge is concurrency-safe and you have the budget.
- **Copy a judge package as your starting point** (`cp -r examples/race-japan-elderly/grader my-task/grader`) and edit the rubric — faster than wiring one from scratch.
- These are the same packages the README's "Rubric Judges" guide documents: https://docs.coralxyz.com/guides/rubric-judge
