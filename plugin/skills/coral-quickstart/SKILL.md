---
name: coral-quickstart
description: The fast path from zero to a running CORAL experiment — what CORAL is and when to reach for it, installing the `coral` CLI, registering a runtime with `coral setup`, and the `.coral_workspace/` convention for pointing CORAL at code you already have and want optimized. Use this whenever the user asks "what is coral", "should I use coral for this", wants to install or get coral set up, hits a "command not found" for coral or doesn't have it installed yet, or says "use coral to optimize / speed up / improve this code" and you need the end-to-end onboarding from install to a launched run. Hands off to `setting-up-coral` (runtime bindings), `creating-a-coral-task` (grader authoring), and `running-coral-experiments` (operating a run) for depth.
---

# CORAL quickstart

**CORAL** is infrastructure for autonomous coding agents: you give it a codebase (`seed/`) and a grader (turns a commit into a number), and it spawns agents in isolated git worktrees that edit code, submit commits, and get scored on a shared leaderboard — looping to push the score up. The agents *are* the optimizer; your grader defines "better".

## When to reach for CORAL

**Good fit:**
- You can express success as a **number** — accuracy, runtime ratio, pass rate, or a rubric-judge score for open-ended work.
- The work is **iterative search**: many attempts at one well-scoped problem (kernel/algorithm optimization, benchmark solving, prompt/program tuning, "make this function faster").
- You want **parallel agents** exploring independently and sharing what works.

**Not a fit:**
- One-shot tasks with no measurable objective.
- Work that needs a human judging every attempt (use a rubric-judge grader if a *model* can score it).

## How a run is shaped

```
you provide:   seed/ (starter code)  +  a grader (commit → number)
coral spawns:  N agents, each in its own git worktree
each agent:    edit code → `coral eval` → grader scores it → read leaderboard → repeat
shared state:  attempts, notes, and skills are visible across agents in real time
```

Two things you build (`seed/` + grader) and one thing you tune (how many agents, which model). Worktrees, scoring daemon, shared state, and restarts are handled for you.

## Get running — four steps

### 1. Install the CLI

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
# or, if you have uv:  uv tool install coral
coral --help      # verify
```

The installer grabs the **latest `coral` release** by default — that's what you want. (Only pin a specific release with `CORAL_VERSION=<tag>` before the curl if you have a reason to.)

### 2. Register a runtime (`coral setup`)

`coral` shells out to a coding-agent CLI (Claude Code, Codex, Cursor, Kiro, OpenCode) — each installed and authenticated separately. Tell coral which to use:

```bash
coral setup            # scans PATH, wizard to create named runtime bindings
coral agents doctor    # validates them, incl. a live auth ping
```

If `doctor`'s live ping fails (expired auth, model typo, "runtime not found" at start) → the `setting-up-coral` skill has the full troubleshooting matrix.

### 3. Build a task — use a `.coral_workspace/`

When the user wants CORAL to optimize **code they already have**, keep every bit of CORAL scaffolding (task config, seed, grader, results) inside a `.coral_workspace/` directory at the root of their project. This keeps coral out of their actual source tree and is trivially gitignored.

> **Act — never answer "optimize this" with a menu.** A request like "use coral to optimize this" (in any language) is a build instruction, not a question. The failure mode to avoid is a process menu like *"1. point me to a task  2. create one  3. optimize outside coral"* — **do not produce that.** A repo with no `task.yaml` isn't ambiguous; it just means you build the task from the current repo. So:
> 1. **Dig for what's already measurable.** Research/framework repos (like SAGA) almost always ship an eval/benchmark script, a test suite, or a headline metric in the README/paper. Find it — that's your optimization target and metric.
> 2. **If no single number is obvious, construct one** by wrapping the repo's existing evaluation. Don't give up and ask just because there's no CORAL scaffold.
> 3. **Scaffold the most plausible target and start building** — a `.coral_workspace/` + draft grader is cheap and reversible. State your assumption in one line ("Optimizing SAGA's <metric> from <script> — building it now; redirect me if you meant something else") and proceed.
> 4. **Last resort only:** if you've actually read the repo and it exposes nothing scorable, propose 2-3 **concrete** targets you found (each with a metric), pick the most likely, and scaffold it — still not a process menu.
>
> Stop before `coral start` (a paid run); everything up to a validated task is autonomous. On Claude Code, delegate this whole grind to the `coral-task-author` subagent.

The mechanical boilerplate (gitignore + `coral init` + copy the code into `seed/`) is bundled as a script — run it from the project root:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/coral-quickstart/scripts/new-coral-workspace.sh" optimize path/to/their_module.py
```

It scaffolds `.coral_workspace/optimize/` and copies the file into `seed/solution.py`, leaving only the grader for you to write. (Equivalent by hand:)

```bash
# from the user's project root
echo ".coral_workspace/" >> .gitignore
mkdir -p .coral_workspace && cd .coral_workspace
coral init optimize && cd optimize
cp ../../path/to/their_module.py seed/solution.py   # the code to optimize
```

Then make the task fit the user's goal — two edits:
- **`task.yaml`** → set `task.description` to what the agents should optimize and the program file's contract (e.g. "`solution.py` must define `run()` and stay correct; we score speedup").
- **the grader** → score the user's actual metric (speedup vs baseline, accuracy on a held-out set, pass rate, …). This is the heart of it → the `creating-a-coral-task` skill walks through grader patterns and the `TaskGrader` API.

### 4. Validate, then launch

```bash
coral validate .                 # confirms the grader scores the seed — the one checkpoint that matters
coral start -c task.yaml         # launch agents (results stay under .coral_workspace/)
coral status                     # watch the leaderboard
```

If `coral validate` succeeds, the grader can score the seed; most "agents are stuck" reports trace to a grader that crashes here. Driving the run from here — monitoring, steering, stopping — is the `running-coral-experiments` skill.

## The workflows (where to go next)

| You want to... | Skill | Commands |
|---|---|---|
| **Set up** runtimes (one-time) | `setting-up-coral` | `coral setup`, `coral agents doctor` |
| **Author** a task / write a grader | `creating-a-coral-task` | `coral init`, `coral validate` |
| **Run / manage** experiments | `running-coral-experiments` | `coral start / status / log / show / resume / stop` |

The eval loop *inside* a run (`coral eval -m "..."` → score → iterate) is driven by the agents themselves — they read it from the `CORAL.md` CORAL generates, so you never run it by hand. Docs: https://docs.coralxyz.com/
