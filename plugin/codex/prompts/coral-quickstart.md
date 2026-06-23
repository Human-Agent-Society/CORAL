# coral-quickstart

Help me with CORAL — infrastructure for autonomous coding agents that edit a codebase, submit commits, and get scored on a shared leaderboard, looping to improve the score.

First check the CLI is installed:

```bash
coral --help
```

If `coral` is missing, install it:

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
# or: uv tool install coral
```

CORAL fits when success is a **number** (a grader) and the work is **iterative search** over one well-scoped problem with parallel agents. It is not a fit for one-shot tasks with no measurable objective.

Two workflows:
- **Author a task** → use `/creating-a-coral-task` (`coral init`, `coral validate`).
- **Run experiments** → use `/running-coral-experiments` (`coral start / status / log / show / resume / stop`).

60-second path:

```bash
coral init my-task && cd my-task   # scaffold task.yaml + seed/ + grader package
# edit seed/solution.py and grader/src/.../grader.py
coral validate .                   # confirm the grader scores the seed
coral start -c task.yaml           # launch agents
coral status                       # watch the leaderboard
```

Docs: https://docs.coralxyz.com/
