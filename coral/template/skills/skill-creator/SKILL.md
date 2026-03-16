---
name: skill-creator
description: Autonomously create, test, and optimize skills by detecting reusable patterns in your own work. Use when you notice repeated tool sequences, recurring code patterns across attempts, or insights that should be captured as a packaged skill. Also use to benchmark and iterate on existing skills.
---

# Skill Creator (Autonomous)

Create skills by analyzing your own work patterns — you are both creator and evaluator. No human input required at any step.

**Core loop:** analyze context → draft SKILL.md → generate test cases → run + grade → iterate → optimize description → package

---

## 1. Context Analysis

Before drafting, identify what skill to build and confirm it doesn't already exist.

### Pattern Detection

Scan these sources for repeated, reusable patterns:

- **Git diffs**: `git log --stat -10` and `git diff HEAD~5` — look for repeated file types, similar transformations, recurring helper scripts written independently across commits
- **Attempt history**: Read `.coral/attempts/` JSON files — which approaches recur? What tool sequences appear in multiple successful attempts?
- **Tool usage**: Review your own transcript — sequences of 3+ tool calls that repeat across tasks are skill candidates
- **Cross-episode notes**: Run `coral notes --read all` — patterns under "Patterns That Work" not yet captured as skills are prime candidates
- **Sibling techniques**: Check `.coral/graph_state/state.yaml` `siblings:` — if multiple agents converged on the same technique independently, it deserves a skill

### Deduplication Check

Before creating a new skill, check existing skills:

```
coral skills
```

Read each relevant `SKILL.md` frontmatter. If an existing skill has 70%+ overlap with your candidate, **update that skill** instead of creating a new one.

### Output

Produce a structured spec before writing:

```
Skill name: <kebab-case>
Purpose: <what it enables, one sentence>
Triggers: <when should this skill activate>
Output format: <what the skill produces>
Source evidence: <which patterns/diffs/insights led to this>
```

---

## 2. Write the SKILL.md

Based on your context analysis, draft the skill.

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

These word counts are approximate and you can feel free to go longer if needed.

**Key patterns:**
- Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next to follow up.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Principle of Lack of Surprise

Skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described.

#### Naming and Description

- Use kebab-case for skill name and directory
- The `description` field is the primary triggering mechanism. Include both what the skill does AND specific contexts for when to use it
- Make descriptions slightly "pushy" to combat under-triggering. Instead of "How to build a dashboard", write "How to build a dashboard. Use this skill whenever the user mentions dashboards, data visualization, internal metrics, or wants to display any kind of data, even if they don't explicitly ask for a 'dashboard.'"
- The description will be programmatically optimized in step 7 — write a good first draft but don't agonize over it

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats:**
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern:**
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

#### Writing Style

Explain to the model **why** things are important rather than relying on heavy-handed MUSTs. Use theory of mind and make the skill general rather than narrow to specific examples. Write a draft, then review it with fresh eyes and improve it.

---

## 3. Generate Test Cases

Create 3-5 test cases derived from the real contexts that triggered your pattern detection.

### Test Case Design

- **Simple case**: The canonical, straightforward application of the skill
- **Complex case**: Multiple interacting aspects, larger input, more steps
- **Edge case**: Unusual input, boundary conditions, minimal context
- **Counter-examples** (1-2): Near-miss scenarios where the skill should NOT apply — these prevent overfitting

### Assertions

Write 2-4 assertions per test case upfront. Good assertions are:
- **Objectively verifiable** — a script or grader can check them unambiguously
- **Discriminating** — they should fail without the skill (or with a bad skill) and pass with a good one
- **Descriptive** — assertion text should read clearly in benchmark output

### Save to evals/evals.json

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Task prompt derived from real pattern",
      "expected_output": "Description of expected result",
      "files": [],
      "expectations": [
        "Output file exists and contains valid JSON",
        "All required fields are present",
        "Processing completes without errors"
      ]
    }
  ]
}
```

See `references/schemas.md` for the full schema.

---

## 4. Run and Grade

This section is one continuous sequence — execute all steps without stopping.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Organize by iteration (`iteration-1/`, `iteration-2/`, etc.) and within that, each test case gets a directory (`eval-0/`, `eval-1/`, etc.).

### Step 1: Spawn all runs in parallel

For each test case, spawn two subagents in the same turn — one with the skill, one without (baseline).

**With-skill run:**
```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <relevant output files>
```

**Baseline run** (same prompt, no skill):
```
Execute this task:
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/without_skill/outputs/
- Outputs to save: <relevant output files>
```

Write an `eval_metadata.json` for each test case. Give each eval a descriptive name.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The task prompt",
  "assertions": ["assertion text 1", "assertion text 2"]
}
```

### Step 2: Capture timing data

When each subagent completes, the task notification contains `total_tokens` and `duration_ms`. Save immediately to `timing.json` in the run directory:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

This data only comes through the notification — capture it as each run completes.

### Step 3: Grade

Once all runs finish, grade each run using the grader agent instructions from `agents/grader.md`. Save results to `grading.json` in each run directory.

The `grading.json` expectations array must use fields `text`, `passed`, and `evidence` (not `name`/`met`/`details`). For assertions checkable programmatically, write and run a script rather than eyeballing it.

### Step 4: Aggregate and analyze

1. **Aggregate into benchmark:**
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   Produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens per configuration (mean ± stddev and delta).

2. **Analyst pass** — read `agents/analyzer.md` and surface patterns the aggregate stats might hide: non-discriminating assertions, high-variance evals, time/token tradeoffs.

3. **Viewer (optional, for debugging):** If you need to inspect outputs visually:
   ```bash
   python eval-viewer/generate_review.py <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     --static <workspace>/iteration-N/review.html
   ```

---

## 5. Iterate

Analyze failures and improve the skill automatically. The goal is to make the skill genuinely better, not to overfit to test cases.

### Improvement Philosophy

1. **Generalize from failures.** Skills will be used across many different prompts. Rather than adding fiddly, overfitted fixes, try different metaphors or recommend different working patterns. It's cheap to experiment.

2. **Keep the prompt lean.** Remove instructions that aren't pulling their weight. Read the transcripts — if the skill causes unproductive work, trim the responsible sections.

3. **Explain the why.** Explain reasoning behind instructions rather than using rigid ALWAYS/NEVER rules. Models with good theory of mind respond better to understanding than to commands.

4. **Bundle repeated work.** If test run transcripts show agents independently writing similar helper scripts, bundle that script into `scripts/` and reference it from the skill.

### Iteration Loop

For each iteration:

1. **Analyze `grading.json` failures** — read `evidence` fields to understand root causes
2. **Read grader's `eval_feedback.suggestions`** — check for assertion quality issues
3. **Apply improvements** to SKILL.md (and scripts/references if needed)
4. **Re-run** into `iteration-<N+1>/`, re-grade, re-aggregate

### Stop Criteria

Stop iterating when any condition is met:

| Condition | Action |
|-----------|--------|
| `pass_rate >= 0.80` AND `delta > 0.15` over baseline | **STOP** — success |
| `pass_rate == 1.0` | **STOP** — perfect |
| `iteration >= 3` | **STOP** — use best version |
| No improvement > 0.05 from previous iteration | **STOP** — plateau reached |
| Regression from previous iteration | **Revert** to best version, STOP |

When stopping, select the iteration with the highest pass_rate as the final version.

---

## 6. Description Optimization

After the skill content is finalized, optimize the frontmatter description for triggering accuracy.

### Generate Trigger Eval Queries

Create 20 eval queries as JSON — 10 should-trigger, 10 should-not-trigger:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

**Quality criteria for queries:**

- Realistic and specific — include file paths, personal context, column names, company names, URLs
- Mix of lengths, tones (formal, casual, abbreviated)
- Some with typos or casual speech

**Should-trigger (10):** Different phrasings of the same intent. Include cases where the user doesn't name the skill explicitly but clearly needs it. Cover uncommon use cases and competitive scenarios where this skill should win.

**Should-not-trigger (10):** Near-misses that share keywords but need something different. Adjacent domains, ambiguous phrasing where naive keyword matching would false-positive. Don't use obviously irrelevant queries — the negatives should be genuinely tricky.

Queries should be substantive enough that Claude would benefit from consulting a skill. Simple one-step queries won't trigger skills regardless of description quality.

### Run the Optimization Loop

Save the eval set to the workspace, then run:

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --verbose
```

This handles the full optimization loop: splits into 60% train / 40% test, evaluates the current description (3 runs per query), proposes improvements based on failures, and iterates up to 5 times. Best description is selected by test score to avoid overfitting.

### Apply Result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter automatically.

---

## 7. Package

Run unconditionally after all optimization is complete:

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

This validates the skill structure and creates a distributable `.skill` file.

---

## Reference Files

The `agents/` directory contains instructions for specialized subagents. Read them when spawning the relevant subagent:

- `agents/grader.md` — Evaluate assertions against outputs
- `agents/comparator.md` — Blind A/B comparison between two outputs
- `agents/analyzer.md` — Analyze benchmark results and why one version beat another

The `references/` directory has schema documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, benchmark.json, etc.

---

## Summary

1. **Analyze** your work patterns for reusable skills
2. **Draft** the SKILL.md following the writing guide
3. **Test** with generated cases (with-skill vs baseline)
4. **Grade** and aggregate results
5. **Iterate** using grading feedback until stop criteria met
6. **Optimize** the description for triggering accuracy
7. **Package** the final skill
