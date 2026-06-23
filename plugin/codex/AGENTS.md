<!--
Paste this block into your project's (or ~/.codex/) AGENTS.md so Codex knows
when to reach for CORAL. It mirrors the Claude Code SessionStart hook.
-->

## CORAL

`coral` is a CLI for running autonomous coding agents against a grader and a leaderboard. If it's installed (`coral --help` succeeds), reach for it when the user wants to **author a task** or **run experiments**; otherwise install it (`uv tool install coral`).

- **Author a task** (`task.yaml` + `seed/` + packaged grader): run `/creating-a-coral-task`. Scaffold with `coral init`, validate with `coral validate .`.
- **Run / manage experiments**: run `/running-coral-experiments`. Drive `coral start / status / log / show / resume / stop`; pass per-run overrides as dotlist args (`agents.count=4`).
- **What is it / install**: run `/coral-quickstart`.

Don't memorize flags — run `coral <cmd> --help`. The in-run eval loop (`coral eval`) is documented in the generated `CORAL.md` each agent reads automatically. Docs: https://docs.coralxyz.com/
