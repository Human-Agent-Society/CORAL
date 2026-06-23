# CORAL plugin

Drive [CORAL](https://github.com/Human-Agent-Society/CORAL) from your own agent harness without memorizing the CLI. **Skills-first, multi-harness, no MCP** (the capability is text guidance + a `coral` Bash call — the agent can already run `coral`; the plugin teaches it *when and how*).

This targets people in **their own** Claude Code / Codex who want to author or run CORAL tasks — not contributors editing the CORAL repo (those skills live in the repo's `.claude/skills/`).

## What's here

```
plugin/
├── .claude-plugin/marketplace.json   # Claude Code marketplace listing the plugin
├── coral-plugin/                     # the Claude Code plugin
│   ├── .claude-plugin/plugin.json
│   ├── skills/
│   │   ├── coral-quickstart/         # what is coral / when to use / install
│   │   ├── creating-a-coral-task/    # author task.yaml + seed/ + grader package
│   │   └── running-coral-experiments/# start / status / log / show / resume / stop
│   └── hooks/
│       ├── hooks.json                # SessionStart → session_start.py
│       └── session_start.py          # install check + context injection
└── codex/                            # Codex distribution (same skills as prompts)
    ├── prompts/*.md                  # ~/.codex/prompts/ custom prompts
    ├── AGENTS.md                     # snippet to paste into your AGENTS.md
    └── install.sh                    # copies prompts into ~/.codex/prompts/
```

## Skills

| Skill | Use when |
|---|---|
| `coral-quickstart` | "what is coral?", "should I use coral?", or `coral` isn't installed yet |
| `creating-a-coral-task` | author a task — `coral init` → edit grader/seed → `coral validate` |
| `running-coral-experiments` | run/manage a run — `coral start / status / log / show / resume / stop` |

The **in-run eval loop** (`coral eval`) is deliberately *not* a skill — every in-run agent already reads it from the generated `CORAL.md`, so a skill would duplicate it. `coral-quickstart` folds in the thin pointer.

## Install — Claude Code

The marketplace and plugin are both in this directory. From a checkout of the CORAL repo:

```
/plugin marketplace add ./plugin
/plugin install coral@coral
```

Or point at the GitHub repo (subpath support depends on your Claude Code version):

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral
```

On session start the hook checks `coral` is on PATH and injects a short context block (install hint if missing, which-skill-for-what if present). Validate the manifest with `claude plugin validate ./plugin/coral-plugin`.

## Install — Codex

```bash
sh plugin/codex/install.sh           # copies prompts into ~/.codex/prompts/
```

Then `/coral-quickstart`, `/creating-a-coral-task`, `/running-coral-experiments` are available in Codex. Paste `plugin/codex/AGENTS.md` into your project (or `~/.codex/`) `AGENTS.md` so Codex reaches for them automatically.

## Other harnesses

Cursor / OpenCode / Kimi follow the same skills-first layout (Superpowers-style) — the skill text is harness-agnostic. Add per-harness manifests under `plugin/<harness>/` as support lands.
