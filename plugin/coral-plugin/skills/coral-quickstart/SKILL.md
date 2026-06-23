---
name: coral-quickstart
description: What CORAL is, when to reach for it, and how to install the `coral` CLI. Use when the user asks "what is coral", "should I use coral for this", or when `coral` isn't installed yet and needs to be set up. Hands off to `creating-a-coral-task` (authoring) and `running-coral-experiments` (operating) for the actual work.
---

# CORAL quickstart

**CORAL** is infrastructure for autonomous coding agents: you give it a codebase (`seed/`) and a grader, and it spawns agents in isolated git worktrees that edit code, submit commits, and get scored on a shared leaderboard — looping to improve the score.

## When to reach for CORAL

Good fit:
- You can express success as a **number** (a grader: accuracy, runtime ratio, pass rate, a rubric-judge score).
- The work is **iterative search** — many attempts at one well-scoped problem (kernel optimization, algorithm design, benchmark solving, prompt/program tuning).
- You want **parallel agents** exploring independently and sharing what works.

Not a fit:
- One-shot tasks with no measurable objective.
- Work that can't be scored without a human in the loop on every attempt (use a rubric-judge grader if a model *can* score it).

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
# or, with uv:
uv tool install coral
```

Pin a version with `CORAL_VERSION=v0.7.0` before the curl. Verify:

```bash
coral --help
```

Each agent runtime you want to use (Claude Code, Codex, Cursor, Kiro, OpenCode) must be installed and authenticated separately — `coral` shells out to them.

## The two workflows

| You want to... | Skill | Commands |
|---|---|---|
| **Author** a task (write a grader + seed) | `creating-a-coral-task` | `coral init`, `coral validate` |
| **Run / manage** experiments | `running-coral-experiments` | `coral start / status / log / show / resume / stop` |

## 60-second path

```bash
coral init my-task          # scaffold task.yaml + seed/ + grader package
cd my-task
# edit seed/solution.py and grader/src/.../grader.py for your problem
coral validate .            # confirm the grader scores the seed
coral start -c task.yaml    # launch agents
coral status                # watch the leaderboard
```

The eval loop *inside* a run (`coral eval -m "..."` → score → iterate) is documented in the `CORAL.md` every in-run agent reads automatically — you don't drive that by hand. Docs: https://docs.coralxyz.com/
