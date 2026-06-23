# CORAL plugin

Drive [CORAL](https://github.com/Human-Agent-Society/CORAL) from your own agent harness without memorizing the CLI. **Skills-first, multi-harness, no MCP** — the capability is text guidance plus a `coral` Bash call, mirroring [obra/superpowers](https://github.com/obra/superpowers). Layout follows the same convention: one shared `skills/` directory, a per-harness manifest (`.claude-plugin/`, `.codex-plugin/`), and per-harness hook configs.

This targets people in **their own** Claude Code / Codex who want to author or run CORAL tasks — not contributors editing the CORAL repo (those skills live in the repo's `.claude/skills/`).

## Layout

```
plugin/                         # this directory IS the plugin
├── .claude-plugin/plugin.json  # Claude Code manifest  → skills/ + hooks/hooks.json
├── .codex-plugin/plugin.json   # Codex manifest        → skills/ + hooks/hooks-codex.json
├── skills/                     # one shared copy, consumed by every harness
│   ├── coral-quickstart/       # what is coral / when to use / install / .coral_workspace flow
│   │   └── scripts/            #   new-coral-workspace.sh (scaffold boilerplate)
│   ├── setting-up-coral/       # register runtimes as bindings (coral setup / agents doctor)
│   ├── creating-a-coral-task/  # author task.yaml + seed/ + grader package
│   │   └── references/         #   grader-api, cookbook, rubric-judges, task-yaml (loaded on demand)
│   └── running-coral-experiments/  # start / status / log / show / resume / stop
│       └── references/         #   steering (resume/fork/heartbeat), scaling-and-ops
├── agents/                     # Claude Code subagents (auto-discovered; Codex doesn't consume these)
│   ├── coral-task-author.md    # code + goal → a validated task in .coral_workspace/
│   └── coral-run-doctor.md     # diagnose a stuck/plateaued run, recommend fixes
├── hooks/
│   ├── hooks.json              # Claude Code SessionStart
│   ├── hooks-codex.json        # Codex SessionStart
│   └── session-start.py        # shared: install check + context injection
└── AGENTS.md                   # optional snippet for harnesses without plugin install

# at the repo root (each harness reads its marketplace from a fixed path):
.claude-plugin/marketplace.json     # Claude Code  — source "./plugin"
.agents/plugins/marketplace.json    # Codex        — git-subdir source, path "./plugin"
```

## Skills

| Skill | Use when |
|---|---|
| `coral-quickstart` | "what is coral?", "should I use coral?", or `coral` isn't installed yet |
| `setting-up-coral` | one-time machine setup — register runtimes as bindings (`coral setup`, `coral agents doctor`) |
| `creating-a-coral-task` | author a task — `coral init` → edit grader/seed → `coral validate` |
| `running-coral-experiments` | run/manage a run — `coral start / status / log / show / resume / stop` |

The **in-run eval loop** (`coral eval`) is deliberately *not* a skill — every in-run agent already reads it from the generated `CORAL.md`, so a skill would duplicate it. `coral-quickstart` folds in the thin pointer.

## Agents (Claude Code)

Two subagents wrap the two grindy, multi-step jobs so the main agent can delegate them and keep its context clean. They're auto-discovered from `agents/`; **Claude Code only** — Codex plugins don't consume subagents, but the same workflows are covered by the skills there.

| Subagent | Delegate when |
|---|---|
| `coral-task-author` | the user wants CORAL pointed at existing code — it scaffolds `.coral_workspace/`, writes the grader, and loops `coral validate` until the seed scores cleanly |
| `coral-run-doctor` | a run is restarting / failing every eval / plateaued — it triages with read-only `coral` commands and returns ranked fixes (it recommends, never restarts/stops) |

The agents lean on the skills above (`creating-a-coral-task`, `running-coral-experiments`) rather than restating them.

## Install — Claude Code

The marketplace manifest lives at the **repo root** (`.claude-plugin/marketplace.json`), so `owner/repo` discovery works:

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral-marketplace
```

Or from a local checkout:

```
/plugin marketplace add .
/plugin install coral@coral-marketplace
```

On session start the hook checks `coral` is on PATH and injects a short context block — an install hint if missing, which-skill-for-what if present. Validate the manifest with `claude plugin validate ./plugin`.

## Install — Codex

Codex (v0.117.0+) has a git-backed plugin marketplace, mirroring Claude Code. The repo ships a Codex marketplace at `.agents/plugins/marketplace.json` (repo root) listing this plugin via a `git-subdir` source pointing at `./plugin`:

```
codex plugin marketplace add Human-Agent-Society/CORAL
codex plugin add coral@coral-marketplace
```

The plugin's `.codex-plugin/plugin.json` wires the shared `skills/` and `hooks/hooks-codex.json` (SessionStart install check). Invoke skills with `$coral-quickstart` (etc.) or let Codex match by description.

**Lighter alternative (no marketplace):** Codex also discovers skills from filesystem dirs and follows symlinks, so you can point a skills dir straight at the repo:

```bash
mkdir -p ~/.agents/skills
ln -s /abs/path/to/CORAL/plugin/skills/* ~/.agents/skills/   # or .agents/skills/ for repo scope
```

The skills-dir route skips the SessionStart hook (it's bound to plugin packaging); paste `AGENTS.md` into your `AGENTS.md` as the substitute.

## Other harnesses

Cursor, OpenCode, and Kimi follow the same shared-`skills/` + per-harness-manifest layout. Add a `.cursor-plugin/` / `.opencode/` / `.kimi-plugin/` manifest pointing at `./skills/` as support lands — no skill content changes needed.

## Publishing

"Published" is per-harness, and only Claude Code has a public target today.

**Claude Code — self-host (works now).** The root `.claude-plugin/marketplace.json` makes the plugin discoverable; anyone can:

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral-marketplace
```

This works even though the plugin lives in a subdir: the marketplace entry's `"source": "./plugin"` resolves relative to the marketplace root (the repo root) after Claude clones the repo.

**Claude Code — community marketplace (optional, review-gated).** To list in `anthropics/claude-plugins-community` so users install via `@claude-community`, submit through the in-app form (claude.ai directory submissions, or the Console form for individuals). Run `claude plugin validate ./plugin` first — the review pipeline runs the same check plus safety screening. Approved plugins are pinned to a commit SHA in the community catalog (their CI handles the subdir via a `git-subdir` source), and the public catalog syncs nightly. Anthropic curates the separate `claude-plugins-official` marketplace at its discretion — there's no submission for it.

**Codex — self-host (works now).** Codex's git-backed marketplace (`.agents/plugins/marketplace.json`) makes the plugin installable today via `codex plugin marketplace add Human-Agent-Society/CORAL` + `codex plugin add coral@coral-marketplace`. Self-serve publishing to the *official* Codex Plugin Directory is "coming soon" per OpenAI — until then, the git-backed marketplace above is the distribution path (same model as Claude self-host).

**Cursor / Kimi / OpenCode.** No public plugin registry yet — distribute via the filesystem routes (e.g. the skills-dir symlink). Being a standalone repo wouldn't change this.

Note: nothing here is automatic. Pushing to this repo does not publish anything; a user must add the marketplace, or you must submit to the community marketplace. Once a user has added the marketplace, new commits update their copy only if auto-update is on.
