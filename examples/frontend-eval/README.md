# frontend-eval — Agentic Evaluator demo task

A CORAL example task that demonstrates the **`AgenticEvaluator`** grader: a persistent Claude agent that uses **Playwright MCP** to browse the generator's live frontend, screenshot it, interact with it, and score it against task-configurable criteria.

This is the GAN-style generator/evaluator architecture from [Anthropic's harness-design-long-running-apps blog post](https://www.anthropic.com/engineering/harness-design-long-running-apps).

## Layout

```
examples/frontend-eval/
├── task.yaml                              # Standalone demo: opus generator, 400 turns
├── skills/
│   └── frontend-design/                   # Ported verbatim from anthropics/skills.
│       ├── SKILL.md                       # Seeded into the generator's .claude/skills/
│       └── LICENSE.txt                    # via agents.skills in task.yaml
├── seed/                                  # Starter the generator's repo is cloned from
│   ├── index.html                         # Starter placeholder
│   ├── README.md                          # Brief for the generator
│   └── .gitignore
└── grader/                                # The grader package
    ├── pyproject.toml
    └── src/agentic_evaluator/
        ├── __init__.py
        ├── grader.py                      # AgenticEvaluator(TaskGrader)
        ├── evaluator_md.py                # Renders the evaluator's CLAUDE.md
        ├── http_server.py                 # Serves the attempt over HTTP for the evaluator
        └── templates/evaluator.md.template
```

## Run it

Smoke test first — cheap, confirms the pipeline actually works on this CORAL checkout before spending an Opus budget:

```bash
uv run coral start -c examples/frontend-eval/task.yaml run.session=local agents.model=haiku agents.max_turns=60
coral log --recent
coral stop
```

Then the real run:

```bash
uv run coral start -c examples/frontend-eval/task.yaml run.session=local

# Watch progress:
coral log --recent
coral show <hash>
```

Each `coral eval` triggers the AgenticEvaluator: it starts an HTTP server, spawns an evaluator agent with Playwright MCP, the evaluator browses the page and writes `evaluation.json` with per-criterion scores + critique, the grader returns a weighted ScoreBundle.

## Criteria

From `task.yaml`:

| Criterion | Weight | What it measures |
|---|---|---|
| Design Quality | 3.0 | Coherent visual identity, distinct mood |
| Originality | 3.0 | Custom decisions vs. AI-slop patterns |
| Craft | 0.5 | Technical execution, hierarchy, responsiveness |
| Functionality | 0.25 | Users can find primary actions, complete tasks |

Each is scored 0.0–1.0. Aggregate = weighted average. Design Quality and
Originality are weighted 6x more than Craft and Functionality combined, on
purpose — see "Design decisions" below.

## Design decisions

- **`session_persistent: false` is mandatory.** With persistence on, the
  evaluator resumes its own session across evals and anchors on prior scores
  — in one pilot, 9 consecutive attempts returned the exact same 4-tuple
  across meaningfully different pages.
- **The generator gets the criteria in its own task description**, not just
  the evaluator — it needs to know what it's optimizing for.
- **Criteria descriptions are short, on purpose.** No fail-example lists,
  reference-site anchors, or score-band tables. The prior evaluator template
  had all of these (see git history) and they narrow the range of designs
  that can score well — a rubric that repeatedly cites "Stedelijk, Tate,
  MoMA PS1" as calibration anchors nudges every attempt toward one register.
- **The `frontend-design` skill (`skills/frontend-design/`) is what forces
  quality, not an elaborate evaluator prompt.** It makes the generator plan a
  design system (palette, type pairing, signature element) and self-critique
  for genericness *before* writing code. This is ported verbatim from
  [anthropics/skills](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
  and wired in via `agents.skills` in `task.yaml` — no CORAL core changes
  needed for this part.

## Adapt to a different task

The grader is generic. To use it for backend APIs, data viz, etc.:

1. Copy `task.yaml`, change `task.description` and the `criteria` list
2. Change `evaluation_instructions` to describe how the evaluator should probe your specific output
3. Point `workspace.repo_path` at a different starter dir

Same grader class handles it. Replace Playwright MCP with a different MCP server by setting `grader.args.mcp_servers` in the task YAML.

## Requirements

- Node + `npx` (the Playwright MCP server is installed on first run via `npx -y @playwright/mcp@<pinned>`; the
  version is pinned in `grader.py` (`PLAYWRIGHT_MCP_VERSION`) so every evaluation drives the same browser tooling).
- A working `claude` CLI that supports `--mcp-config` and `--strict-mcp-config`.
  This grader passes those via `runtime_options["mcp_config"]` on
  `ClaudeCodeRuntime.start()` — a small addition to CORAL core
  (`coral/agent/builtin/claude_code.py`) that upstream's rewritten
  sandbox/permission model doesn't wire up on its own. If you're on a CORAL
  checkout that predates this, the evaluator will spawn but never see
  Playwright tools.
- `ANTHROPIC_API_KEY` in the environment (or a CORAL gateway).
