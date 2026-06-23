<!--
Optional: paste this block into your project's (or ~/.codex/) AGENTS.md.
Installing the plugin already surfaces the skills + SessionStart hook; this
snippet is a lightweight alternative for harnesses where you'd rather not
install the plugin but still want the agent to reach for CORAL.
-->

## CORAL

`coral` is a CLI for running autonomous coding agents against a grader and a leaderboard. If it's installed (`coral --help` succeeds), reach for it when the user wants to **author a task** or **run experiments**; otherwise install it (`uv tool install coral`).

- **Author a task** (`task.yaml` + `seed/` + packaged grader): use the `creating-a-coral-task` skill. Scaffold with `coral init`, validate with `coral validate .`.
- **Run / manage experiments**: use the `running-coral-experiments` skill. Drive `coral start / status / log / show / resume / stop`; pass per-run overrides as dotlist args (`agents.count=4`).
- **What is it / install**: use the `coral-quickstart` skill.

Don't memorize flags — run `coral <cmd> --help`. The in-run eval loop (`coral eval`) is documented in the generated `CORAL.md` each agent reads automatically. Docs: https://docs.coralxyz.com/
