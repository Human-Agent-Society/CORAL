# running-coral-experiments

Help me run and manage a CORAL experiment. Five verbs drive a run: **start → status → log/show → resume → stop**. Prefer `coral <cmd> --help` over guessing flags. Needs an existing task (`task.yaml` + `seed/` + grader) — if there isn't one, use `/creating-a-coral-task`.

**Launch:**

```bash
coral start -c task.yaml                                  # auto-tmux
coral start -c task.yaml agents.count=4 agents.model=opus # dotlist overrides (per-run)
coral start -c task.yaml run.verbose=true run.ui=true     # verbose + web dashboard
coral start -c task.yaml run.session=local                # no tmux
```

**Monitor:**

```bash
coral status            # agent health + leaderboard
coral runs [--all]      # active (or all) runs
coral ui --port 8420    # web dashboard
```

**Read results** (`<hash>` from `coral log`/`status`):

```bash
coral log [-n 5 --recent] [--search KW --agent agent-1]
coral show <hash> [--diff]
coral notes [--search KW --read N]
coral skills [--read NAME]
```

**Steer / resume:**

```bash
coral resume                                  # resume latest run
coral resume -i "Try greedy approaches"       # inject an instruction
coral resume --from <hash> -i "..."           # fork: reset agent to an attempt, then steer
coral export <hash> -b winning-idea           # export an attempt as a git branch
```

**Stop:**

```bash
coral stop [--all]
```

Stopping preserves all results/notes/leaderboard — resume or inspect later. `coral eval / diff / revert / checkout` are agent-side (run inside a worktree during a run); as operator you rarely touch them.

CLI reference: https://docs.coralxyz.com/cli/reference
