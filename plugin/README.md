# CORAL plugin

Drive [CORAL](https://github.com/Human-Agent-Society/CORAL) from your own agent harness without memorizing the CLI. **Skills-first, multi-harness, no MCP** — the capability is text guidance plus a `coral` Bash call, mirroring [obra/superpowers](https://github.com/obra/superpowers). Layout follows the same convention: one shared `skills/` directory, a per-harness manifest (`.claude-plugin/`, `.codex-plugin/`), and per-harness hook configs.

This targets people in **their own** Claude Code / Codex who want to author or run CORAL tasks — not contributors editing the CORAL repo (those skills live in the repo's `.claude/skills/`).

## Layout

```
plugin/                         # this directory IS the plugin
├── .claude-plugin/plugin.json  # Claude Code manifest  → skills/ + hooks/hooks.json
├── .codex-plugin/plugin.json   # Codex manifest        → skills/ + hooks/hooks-codex.json
├── skills/                     # one shared copy, consumed by every harness
│   ├── coral-quickstart/       # what is coral / when to use / install
│   ├── creating-a-coral-task/  # author task.yaml + seed/ + grader package
│   └── running-coral-experiments/  # start / status / log / show / resume / stop
├── hooks/
│   ├── hooks.json              # Claude Code SessionStart
│   ├── hooks-codex.json        # Codex SessionStart
│   └── session-start.py        # shared: install check + context injection
└── AGENTS.md                   # optional snippet for harnesses without plugin install

# at the repo root (required for `owner/repo` marketplace discovery):
.claude-plugin/marketplace.json # lists this plugin with source "./plugin"
```

## Skills

| Skill | Use when |
|---|---|
| `coral-quickstart` | "what is coral?", "should I use coral?", or `coral` isn't installed yet |
| `creating-a-coral-task` | author a task — `coral init` → edit grader/seed → `coral validate` |
| `running-coral-experiments` | run/manage a run — `coral start / status / log / show / resume / stop` |

The **in-run eval loop** (`coral eval`) is deliberately *not* a skill — every in-run agent already reads it from the generated `CORAL.md`, so a skill would duplicate it. `coral-quickstart` folds in the thin pointer.

## Install — Claude Code

The marketplace manifest lives at the **repo root** (`.claude-plugin/marketplace.json`), so `owner/repo` discovery works:

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral
```

Or from a local checkout:

```
/plugin marketplace add .
/plugin install coral@coral
```

On session start the hook checks `coral` is on PATH and injects a short context block — an install hint if missing, which-skill-for-what if present. Validate the manifest with `claude plugin validate ./plugin`.

## Install — Codex

Codex reads the same `skills/` via `.codex-plugin/plugin.json`. Point Codex at this plugin per its plugin-install flow, or drop `plugin/skills/` into a Codex skills directory (`.agents/skills/` in a repo, or `~/.agents/skills/`) — the `SKILL.md` frontmatter is harness-agnostic. The `AGENTS.md` snippet is an alternative for surfacing CORAL without installing the plugin.

## Other harnesses

Cursor, OpenCode, and Kimi follow the same shared-`skills/` + per-harness-manifest layout. Add a `.cursor-plugin/` / `.opencode/` / `.kimi-plugin/` manifest pointing at `./skills/` as support lands — no skill content changes needed.
