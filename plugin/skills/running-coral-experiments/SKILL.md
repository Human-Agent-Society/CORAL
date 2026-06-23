---
name: running-coral-experiments
description: Run and manage CORAL experiments from the operator side — launch agents with `coral start` (config + dotlist overrides, model/count, tmux vs local session), monitor with `coral status` and the web dashboard, read results with `coral log` / `coral show`, and drive the loop with `coral resume` (inject instructions, fork from an attempt) and `coral stop`. Use whenever the user wants to start a CORAL run, check on agents, read scores/leaderboard, resume or steer a run, or stop one.
---

# Running CORAL experiments

You drive a run with five verbs: **start → status → log/show → resume → stop**. Everything else is a flag on those. Prefer `coral <cmd> --help` over guessing flags.

Prereq: a task (`task.yaml` + `seed/` + grader package). If there isn't one yet, that's the `creating-a-coral-task` skill. Each runtime CLI (claude_code, codex, ...) must be installed and authenticated separately.

## Launch

```bash
coral start -c task.yaml                                  # auto-tmux session
coral start -c task.yaml agents.count=4 agents.model=opus # dotlist overrides (no quotes needed)
coral start -c task.yaml run.verbose=true run.ui=true     # verbose logs + web dashboard
coral start -c task.yaml run.session=local                # no tmux (foreground-style)
```

- **Dotlist overrides** (`key.subkey=value`) override anything in `task.yaml` for this run only — the cleanest way to sweep count/model without editing the file.
- `run.session`: `tmux` (default; detachable), `local`, or `docker`.
- Each run lands in `results/<task-slug>/<timestamp>/`. The agents work in isolated git worktrees; the grader daemon scores their commits and writes a leaderboard.

## Monitor

```bash
coral status            # agent health + leaderboard snapshot
coral runs              # active runs (across tasks); --all for finished too
coral ui --port 8420    # web dashboard (live leaderboard, logs, DAG view)
```

`coral status` is the quick pulse: which agents are alive, how many evals, current best score. If an agent looks stuck or keeps restarting, that's a debugging question (grader crashing on every submission, bad task.yaml) — check `coral log` for repeated identical failures.

## Read results

```bash
coral log                                  # top 20 attempts by score
coral log -n 5 --recent                    # most recent instead of best
coral log --search "kernel" --agent agent-1
coral show <hash>                          # one attempt: score, explanation, files changed
coral show <hash> --diff                   # full diff of that attempt
coral notes [--search KW] [--read N]       # agent-written markdown notes
coral skills [--read NAME]                 # shared skills agents built
```

The `<hash>` is the commit hash shown in `coral log` / `coral status`. Use `coral show <hash> --diff` to see exactly what a top-scoring attempt did.

## Steer and resume

```bash
coral resume                               # resume the latest run (sessions restored)
coral resume -i "Try greedy approaches first"      # inject an instruction at resume
coral resume --from <hash> -i "Continue this fork"  # reset an agent to an attempt, then steer
coral export <hash> -b winning-idea        # export an attempt's commit as a normal git branch
```

`resume` is how you nudge a run without restarting it: stop, then `coral resume -i "..."` to inject guidance the agents read on their next loop. `--from <hash>` forks: it resets an agent to a past attempt before injecting — useful to revive a promising line that later regressed.

## Stop

```bash
coral stop          # stop the current/latest run
coral stop --all    # stop every active run
```

Stopping leaves all results, notes, and the leaderboard on disk — you can `coral resume` later or just inspect with `coral log` / `coral show`.

## Typical loop

```bash
coral validate .                                   # grader scores the seed (do this once)
coral start -c task.yaml agents.count=2            # launch
coral status                                       # ... check periodically
coral log -n 5 --recent                            # see what agents are trying
coral show <best-hash> --diff                      # inspect the leader
coral resume -i "Focus on the inner loop"          # steer if they plateau
coral stop                                         # done
```

Note: `coral eval / diff / revert / checkout` are **agent-side** commands run *inside* a worktree during a run — agents already know them from the generated `CORAL.md`. As the operator you rarely touch them; you drive the verbs above. Full CLI reference: https://docs.coralxyz.com/cli/reference
