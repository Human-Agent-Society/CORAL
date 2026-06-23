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
│   ├── setting-up-coral/       # register runtimes as bindings (coral setup / agents doctor)
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
| `setting-up-coral` | one-time machine setup — register runtimes as bindings (`coral setup`, `coral agents doctor`) |
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

Codex has no marketplace-style install. It discovers skills from filesystem directories, and follows symlinks — so point a Codex skills dir at this repo's `skills/`:

```bash
# user-level (available in every project)
mkdir -p ~/.agents/skills
ln -s "$(pwd)/plugin/skills/"* ~/.agents/skills/

# or repo-level (scoped to one project, run from that project root)
mkdir -p .agents/skills
ln -s /abs/path/to/CORAL/plugin/skills/* .agents/skills/
```

Invoke with `$coral-quickstart` (etc.), or let Codex pick by description match. The SessionStart install-check hook is bound to Codex's *plugin* packaging path, not loose skills, so it won't run via the skills-dir route — paste `AGENTS.md` into your project (or `~/.codex/`) `AGENTS.md` as the lightweight substitute. The `.codex-plugin/plugin.json` manifest is a placeholder for when Codex exposes a plugin-install flow that consumes it; nothing reads it today.

## Other harnesses

Cursor, OpenCode, and Kimi follow the same shared-`skills/` + per-harness-manifest layout. Add a `.cursor-plugin/` / `.opencode/` / `.kimi-plugin/` manifest pointing at `./skills/` as support lands — no skill content changes needed.

## Publishing

"Published" is per-harness, and only Claude Code has a public target today.

**Claude Code — self-host (works now).** The root `.claude-plugin/marketplace.json` makes the plugin discoverable; anyone can:

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral
```

This works even though the plugin lives in a subdir: the marketplace entry's `"source": "./plugin"` resolves relative to the marketplace root (the repo root) after Claude clones the repo.

**Claude Code — community marketplace (optional, review-gated).** To list in `anthropics/claude-plugins-community` so users install via `@claude-community`, submit through the in-app form (claude.ai directory submissions, or the Console form for individuals). Run `claude plugin validate ./plugin` first — the review pipeline runs the same check plus safety screening. Approved plugins are pinned to a commit SHA in the community catalog (their CI handles the subdir via a `git-subdir` source), and the public catalog syncs nightly. Anthropic curates the separate `claude-plugins-official` marketplace at its discretion — there's no submission for it.

**Codex / Cursor / Kimi / OpenCode.** No public plugin registry exists yet. Distribute via the filesystem routes above (e.g. the Codex skills-dir symlink) until those ecosystems ship a registry. This is the same way superpowers reaches non-Claude harnesses — being a standalone repo wouldn't change it.

Note: nothing here is automatic. Pushing to this repo does not publish anything; a user must add the marketplace, or you must submit to the community marketplace. Once a user has added the marketplace, new commits update their copy only if auto-update is on.
