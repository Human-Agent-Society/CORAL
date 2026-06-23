# Steering a run: resume, fork, and heartbeat tuning

How to influence a run that's already going — inject guidance, revive a promising line, or change how often agents pause to reflect.

## Resume and inject guidance

`coral resume` restarts a stopped run with sessions restored. The `-i/--instruction` flag is the main steering lever: the text is injected so agents read it on their next loop.

```bash
coral resume                                   # resume latest run as-is
coral resume -i "Stop tuning learning rate; try a different architecture"
coral resume --task my-task --run <id> -i "..."   # disambiguate when several runs exist
coral resume agents.model=opus                 # resume with a dotlist override
```

Workflow: `coral stop`, inspect with `coral log`/`coral show`, then `coral resume -i "..."`. Use this when agents are converging on a dead end or you've spotted something in the diffs they should know.

## Fork from a past attempt

`--from <hash>` resets an agent's worktree to a previous commit *before* injecting — use it to revive a strong line that later regressed.

```bash
coral resume --from a1b2c3d -i "This version scored best — continue from here, don't undo the caching"
```

The `<hash>` is from `coral log`/`coral status`. To pull a winning attempt out as a normal git branch (e.g. to ship it), use export instead:

```bash
coral export a1b2c3d -b winning-idea       # creates branch winning-idea in the run repo
coral export a1b2c3d -b winning-idea -f    # overwrite if the branch exists
```

## Heartbeat actions — the reflection cadence

The manager periodically interrupts each agent to inject a prompt. Four actions ship by default:

| Action | Trigger | Default | Scope | Notes |
|---|---|---|---|---|
| `reflect` | interval | every **1** eval | per-agent | always local (protected) |
| `consolidate` | interval | every **10** evals | global | always global, can't be removed (protected) |
| `pivot` | plateau | after **5** non-improving evals | per-agent | fires when stuck |
| `lint_wiki` | interval | every **10** evals | global | tidies shared notes |

- **interval** triggers fire every N evals; **plateau** triggers fire after N evals with no improvement.
- **global** counts evals across all agents; local counts per-agent.

## Tuning the cadence at runtime

```bash
coral heartbeat                                # show current config (default subcommand)
coral heartbeat set reflect --every 3          # reflect less often (every 3 evals)
coral heartbeat set pivot --every 2 --trigger plateau --epsilon 0.001
                                               # pivot sooner; epsilon = min delta that counts as improvement
coral heartbeat set review --every 5 --prompt "Summarize what's working and what isn't"
                                               # custom action (non-built-in REQUIRES --prompt)
coral heartbeat remove review                  # delete a custom action
coral heartbeat reset                          # revert to the task's defaults
```

Flags on `set`: `--every N` (required), `--trigger interval|plateau`, `--global` (use the shared counter), `--epsilon F` (plateau only — minimum score delta to count as progress), `--prompt "..."` (required for non-built-in actions). When several runs exist, add `--task`/`--run` to disambiguate.

`reflect` (protected) is always local and `consolidate` (protected) is always global — you can change their cadence but not their scope, and you can't remove them.

### When to touch heartbeats

- **Agents thrash / reflect too much** on a fast-eval task → raise `reflect --every` so they spend more time iterating.
- **Agents grind on a dead end** → lower `pivot --every` (and set a small `--epsilon`) so they're nudged to change approach sooner.
- **Long, expensive evals** → consolidation every 10 may be too rare or too frequent; tune to taste.

Defaults are good for most runs — reach for this when you see a specific pathology in `coral log`, not preemptively.
