# Scaling, budget classes, and troubleshooting

Operator-side knobs beyond the basic five verbs, plus a diagnostic playbook for runs that misbehave.

## Budget classes — what `coral log`/`status` actually show

Every attempt is classified, and the default views **hide the noise**:

| Class | What it is |
|---|---|
| `real` | a genuine optimization attempt (the default; what you normally want to see) |
| `tune` | submitted with `coral eval --tune` — a cheap hyperparameter probe; doesn't count against plateau/heartbeat budgets |
| `grader_error` | the grader timed out or threw |

```bash
coral log                  # real attempts only, top 20 by score
coral log --all            # include tune + grader_error
coral log --class tune     # only tune-mode probes
coral log --class grader_error   # surface graders that are crashing — first stop when a run looks unhealthy
coral status --all         # leaderboard incl. tune/error
```

If `coral status` looks empty but agents are clearly working, check `coral log --class grader_error` — the grader may be failing every submission.

## Scaling out: more agents, sweeps, islands

```bash
coral start -c task.yaml agents.count=8 agents.model=opus      # bigger fleet
coral start -c task.yaml agents.count=4 agents.stagger_seconds=10   # stagger spawns
```

**Islands** partition agents into isolated sub-populations (separate attempts/notes/skills) with periodic migration of strong agents between them — broader exploration than one flat pool. Configured in `task.yaml` or via dotlist:

```bash
coral start -c task.yaml islands.count=3 \
  islands.migration.every=50 islands.migration.max_per_cycle=2
```

`islands.migration.dest_weighting` is `score` (route toward stronger islands), `uniform`, or `round_robin`. `coral status`/`log` show the aggregate across all islands.

## LiteLLM gateway (custom models / cost tracking)

Route agent model traffic through a LiteLLM gateway to log calls, track cost, add fallbacks, or point agents at a custom/self-hosted model:

```bash
coral start -c task.yaml agents.gateway.enabled=true \
  agents.gateway.port=4000 agents.gateway.config=./litellm_config.yaml
```

`agents.gateway.api_key` is auto-generated if empty. Full gateway setup: https://docs.coralxyz.com/guides/gateway

## Reading the shared brain

Agents accumulate shared state you can inspect any time:

```bash
coral notes                      # list agent-written notes
coral notes --read 3             # read note #3
coral notes --search "caching"   # search notes
coral notes --history            # checkpoint history of shared state
coral notes --diff <hash>        # what changed in a checkpoint
coral skills                     # skills agents have built for themselves
coral skills --read <name>       # read one
```

Notes and skills are where agents record what's working — a fast way to understand *why* the leader is winning without reading every diff.

## Troubleshooting playbook

| Symptom | Likely cause | What to check / do |
|---|---|---|
| Every eval fails identically, score never moves | Grader crashes on the seed | `coral log --class grader_error`; reproduce with `coral validate .`. Fix the grader, then `coral resume`. |
| An agent keeps restarting | Repeated crash inside the runtime, or it exits cleanly each loop | `coral status` for restart counts; `coral log --agent <id>` for the pattern. The restart-burst breaker pauses an agent that crashes too fast. |
| `coral status` shows agents alive but no attempts | Submissions stuck pending, or grader daemon down | `coral log --all` to see pending; confirm the daemon is up (it's a sibling process — `coral status` reports it). |
| Scores plateau early | Agents stuck on one idea | Lower `pivot` plateau threshold (see [steering.md](steering.md)) or `coral resume -i "..."` with a new direction; consider `--from <hash>` to fork a better line. |
| Leaderboard looks upside down | `grader.direction` wrong | This is a task-authoring bug — fix `direction` in `task.yaml` (the `creating-a-coral-task` skill). |
| Run won't resume / picks the wrong run | Multiple runs for the task | Disambiguate: `coral runs --all` to list, then `coral resume --task <name> --run <id>`. |

Most run-health questions answer themselves from three commands: `coral status` (who's alive), `coral log --class grader_error` (is the grader healthy), and `coral show <hash> --diff` (what the leader actually did). Full CLI reference: https://docs.coralxyz.com/cli/reference
