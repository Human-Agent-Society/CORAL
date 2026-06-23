# task.yaml reference

Every block, with defaults. Only `task.name`, `task.description`, `grader.entrypoint`, and `workspace.repo_path` really need your attention — the rest have sane defaults. `coral init` writes a minimal version; this is the full surface for when you need a knob.

Anything here can also be set per-run on the command line as a dotlist override (`coral start -c task.yaml agents.count=4`) without editing the file.

## task

```yaml
task:
  name: "My Task"
  description: |          # rendered verbatim into CORAL.md — this IS the agent's brief
    What to optimize, the program file's name, and its exact contract
    (e.g. "solution.py must print a single float to stdout; higher is better").
  tips: |                 # optional, also rendered into CORAL.md
    - Eval timeout is 300s. Note constraints, the baseline score, scoring details.
```

`description` is the single most important field for agent behavior — it's the whole brief. Name the program file and its I/O contract explicitly; agents can't infer what your grader expects.

## grader

```yaml
grader:
  entrypoint: "my_task_grader.grader:Grader"   # REQUIRED — "module.path:ClassName"
  setup:
    - "uv pip install -e ./grader"             # runs once in .coral/private/grader_venv/
  timeout: 300                  # seconds per eval; 0 = no limit (self.timeout becomes None)
  direction: maximize           # maximize | minimize — leaderboard ordering
  args:                         # arbitrary dict, read via self.args in the grader
    program_file: "solution.py"
  private: []                   # extra files/dirs copied into .coral/private/ (hidden from agents)
  max_pending_per_agent: 1      # cap on in-flight (ungraded) submissions per agent
  parallel:
    max_workers: 1              # daemon concurrency — bump ONLY if the grader is concurrency-safe
```

- **`setup` vs `workspace.setup`**: grader-only deps (judge libs, scoring tools) go in `grader.setup` (installed in the grader venv). The task's *runtime* deps (numpy, torch — what the agent's code imports) go in `workspace.setup` (installed in each agent worktree). Putting runtime deps in `grader.setup` is the classic "works in validate, fails in the run" bug.
- **`direction`**: "ratio vs baseline, higher better" → `maximize`; "raw error / latency" → `minimize`. Getting this backwards silently ranks the leaderboard upside down.
- **`parallel.max_workers`**: leave at 1 unless the grader provably has no shared-resource contention (ports, GPUs, scratch dirs, fixed temp paths).

## agents

```yaml
agents:
  count: 1                      # raise once the task is stable
  runtime: claude_code          # claude_code | codex | cursor | kiro | opencode | "pkg.module:Cls"
  model: sonnet                 # haiku | sonnet | opus | any runtime-resolvable string
  binding: claude-opus          # OR reference a user-level binding (see setting-up-coral)
  max_turns: 0                  # turns per session before restart; 0 = no limit
  timeout: 1200                 # stall watchdog (seconds)
  stagger_seconds: 0            # delay between spawning successive agents
  research: true                # allow an initial web-search/orientation step
  warmstart:
    enabled: false              # optional research phase before the loop
  assignments:                  # OR a mixed team instead of count/runtime/model:
    - binding: researcher
      count: 1
    - binding: implementer
      count: 3
  gateway:
    enabled: false              # route agent model traffic through a LiteLLM gateway
    port: 4000
    config: ""                  # path to litellm_config.yaml
    api_key: ""                 # master key; auto-generated if empty
```

Use **either** `count`+`runtime`+`model` (one homogeneous fleet) **or** `assignments` (a mixed team). `binding:` pulls runtime/model/options from a user-level binding so `task.yaml` stays portable — see the `setting-up-coral` skill.

## workspace

```yaml
workspace:
  repo_path: "./seed"           # MUST point at your seed dir — the code agents start from
  results_dir: "./results"      # where runs land
  setup:                        # runs in EACH agent worktree before the loop starts
    - "uv pip install numpy scipy"   # task RUNTIME deps go here
```

`repo_path` pointing at the task root instead of `./seed` is the most common authoring mistake — the grader then sees `task.yaml` and `grader/` inside `codebase_path`.

## islands (advanced)

Partition agents into isolated sub-populations with their own attempts/notes/skills, with periodic migration of strong agents between them. Single-island (default) needs none of this.

```yaml
islands:
  count: 1                      # >1 enables islands
  migration:
    enabled: true
    every: 50                   # global evals between migration cycles
    rank_window: 20             # "best agent" = max over last N evals
    min_evals: 3                # candidate needs >= N attempts to migrate
    dest_weighting: score       # score | uniform | round_robin
    max_per_cycle: 2
```

## sharing

```yaml
sharing:
  attempts: true                # agents see each other's scored attempts
  notes: true                   # shared notes visible across agents
  skills: true                  # shared skills visible across agents
```

Turn pieces off to make agents explore more independently. Full schema with every field: https://docs.coralxyz.com/api/config
