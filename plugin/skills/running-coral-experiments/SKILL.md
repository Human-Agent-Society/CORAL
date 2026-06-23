---
name: running-coral-experiments
description: Run and manage CORAL experiments from the operator side — launch agents with `coral start` (dotlist overrides, model/count, tmux vs local), monitor with `coral status` / `coral log` / `coral show` / the web dashboard, and drive the loop with `coral resume` (inject instructions, fork from an attempt), `coral heartbeat` (tune reflection cadence), and `coral stop`. Use whenever the user wants to start a CORAL run, check on agents, read scores/leaderboard, steer or resume a run, diagnose agents that keep restarting or fail every eval, scale to more agents or islands, or stop a run. Deep references for steering/heartbeat tuning and scaling/troubleshooting live alongside this skill.
---

# Running CORAL experiments

You drive a run with five verbs: **start → status → log/show → resume → stop**. Everything else is a flag on those or a deeper topic in the references. Prefer `coral <cmd> --help` over guessing flags.

**Prereq:** a task (`task.yaml` + `seed/` + grader package) that passes `coral validate .`. No task yet → that's the `creating-a-coral-task` skill. Each runtime CLI must be installed and authenticated → the `setting-up-coral` skill.

## 1. Launch

```bash
coral start -c task.yaml                                  # auto-tmux session
coral start -c task.yaml agents.count=4 agents.model=opus # dotlist overrides (no quotes needed)
coral start -c task.yaml run.verbose=true run.ui=true     # verbose logs + web dashboard
coral start -c task.yaml run.session=local                # foreground, no tmux
```

- **Dotlist overrides** (`key.subkey=value`) beat `task.yaml` for this run only — the clean way to sweep count/model without editing the file.
- `run.session`: `tmux` (default, detachable) · `local` (foreground) · `docker`.
- Each run lands in `results/<task-slug>/<timestamp>/`; agents work in isolated git worktrees and the grader daemon scores their commits.

## 2. Monitor

```bash
coral status            # agent health + leaderboard snapshot (the quick pulse)
coral runs              # active runs across tasks; --all includes finished
coral ui --port 8420    # web dashboard: live leaderboard, logs, DAG
```

`coral status` answers "who's alive, how many evals, current best". If it looks healthy but scores never move, jump to budget classes + troubleshooting in [references/scaling-and-ops.md](references/scaling-and-ops.md).

## 3. Read results

```bash
coral log                              # top 20 real attempts by score
coral log -n 5 --recent                # most recent instead of best
coral log --search "kernel" --agent agent-1
coral log --class grader_error         # surface crashing graders (first stop when unhealthy)
coral show <hash>                      # one attempt: score, explanation, files changed
coral show <hash> --diff               # full diff — see exactly what the leader did
```

`<hash>` comes from `coral log`/`coral status`. By default `coral log` hides `tune` and `grader_error` attempts; `--all` shows them, `--class {real|tune|grader_error}` filters to one. What the classes mean → [references/scaling-and-ops.md](references/scaling-and-ops.md).

## 4. Steer and resume

```bash
coral resume                                   # resume latest run, sessions restored
coral resume -i "Try greedy approaches first"  # inject guidance agents read next loop
coral resume --from <hash> -i "Continue this fork"   # reset an agent to an attempt, then steer
coral export <hash> -b winning-idea            # export an attempt's commit as a git branch
```

`resume -i` is how you nudge a run without restarting from scratch (stop → resume with an instruction). `--from` forks a promising line that later regressed. You can also retune the reflection cadence — `coral heartbeat set/remove/reset` — to make agents reflect less, pivot sooner, etc. Both topics, with worked examples: [references/steering.md](references/steering.md).

## 5. Stop

```bash
coral stop          # stop the current/latest run (picker if several)
coral stop --all    # stop every active run
```

Stopping leaves all results, notes, and the leaderboard on disk — `coral resume` later, or just inspect with `coral log`/`coral show`.

## Typical loop

```bash
coral validate .                            # grader scores the seed (once)
coral start -c task.yaml agents.count=2     # launch
coral status                                # ... check periodically
coral log -n 5 --recent                     # see what agents are trying
coral show <best-hash> --diff               # inspect the leader
coral resume -i "Focus on the inner loop"   # steer if they plateau
coral stop                                  # done
```

## Going deeper

- **Steer / fork / heartbeat tuning** → [references/steering.md](references/steering.md)
- **Budget classes, islands, gateway, troubleshooting matrix** → [references/scaling-and-ops.md](references/scaling-and-ops.md)

Note: `coral eval / diff / revert / checkout / wait` are **agent-side** commands run *inside* a worktree during a run — agents already know them from the generated `CORAL.md`. As the operator you rarely touch them; you drive the verbs above. Full CLI reference: https://docs.coralxyz.com/cli/reference
