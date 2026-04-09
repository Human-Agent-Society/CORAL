# Examples

Example task configurations for CORAL. Each directory contains a `task.yaml` and any supporting files (graders, seed code, data).

To run any example:

```bash
coral start --config examples/<name>/task.yaml
```

## Task Structure

Every task directory follows the same layout:

```
my_task/
├── task.yaml              # Task configuration (required)
├── eval/
│   ├── grader.py          # Grading logic (required. Entrypoint defined in grader.args.program_file)
│   ├── xxx.py             # Other helper tools (Optional)
│   └── answers/           # Ground-truth data, if needed
│       └── ...
└── seed/                  # Initial codebase given to agents
    ├── solution.py        # Starter code the agents will modify
    ├── Dockerfile         # Your custom dockerfile for your task (Optinoal)
    ├── opencode.json      # Your custom opencode config (Optional)
    └── data/              # Any input data (datasets, configs, etc. Optional)
        └── ...
```

### `task.yaml`

The central configuration file. All available fields (with defaults):

```yaml
task:
  name: "My Task"                    # Task name (required)
  description: |                     # Full problem description shown to agents (required)
    What the agent should do.
  tips: |                            # Hints shown to agents (timeouts, constraints, etc.)
    - Eval timeout is 120s.

grader:
  timeout: 300                       # Max seconds per evaluation (default: 300)
  direction: maximize                # "maximize" or "minimize" (default: maximize)
  type: ""                           # Grader type; empty = auto-discover from eval/grader.py
  module: ""                         # Python module path for custom graders
  args:                              # Arbitrary kwargs passed to the grader
    program_file: "solution.py"
  private:                           # Files/dirs copied to .coral/ (hidden from agents)
    - "answers/"

agents:
  count: 1                           # Number of concurrent agents (default: 1)
  runtime: claude_code               # "claude_code", "opencode", or "codex" (default: claude_code)
  model: sonnet                      # Model name or path (default: sonnet)
  max_turns: 200                     # Max agent turns before stopping (default: 200)
  timeout: 3600                      # Agent-level timeout in seconds (default: 3600)
  research: true                     # Enable web search / literature review (default: true)
  stagger_seconds: 0                 # Delay between spawning each agent (default: 0)
  gateway:                           # LiteLLM gateway for routing model traffic
    enabled: false
    port: 4000
    config: "./litellm_config.yaml"
    api_key: ""                      # Auto-generated if empty
  heartbeat:                         # Periodic agent self-reflection actions
    - name: reflect
      every: 1                       # Trigger every N evals
      global: false                  # false = per-agent count, true = global count
      trigger: interval              # "interval" or "plateau"
    - name: consolidate
      every: 10
      global: true
      trigger: interval
    - name: pivot
      every: 5
      trigger: plateau               # Triggers after N evals with no improvement

sharing:
  attempts: true                     # Share attempt history across agents (default: true)
  notes: true                        # Share notes across agents (default: true)
  skills: true                       # Share skills across agents (default: true)

workspace:
  repo_path: "./examples/my_task/seed"  # Path to seed directory (default: ".")
  results_dir: "./results"              # Where run outputs are stored (default: ./results)
  setup:                                # Shell commands run once per worktree before agents start
    - "uv pip install numpy scipy"

run:
  verbose: false                     # Verbose output (default: false)
  ui: false                          # Launch web dashboard (default: false)
  session: tmux                      # "local", "tmux", or "docker" (default: tmux)
  docker_image: ""                   # Custom docker image; empty = auto-build from docker/<runtime>/ (default: "")
```

### `eval/grader.py`

Contains the grading logic. Typically a `TaskGrader` subclass that implements an `evaluate()` method. The grader receives the codebase path and task list, runs the agent's solution, and returns a `ScoreBundle`.

### `seed/`

The starting codebase that gets copied into each agent's git worktree. This is what agents see when they begin working. It should contain starter code (with a function signature the grader expects) and any data files the solution needs at runtime.

## Examples Overview

| Example | Description | Direction |
|---------|-------------|-----------|
| [circle_packing](#circle_packing) | Pack 26 circles in a unit square to maximize sum of radii | Maximize |
| [erdos](#erdos) | Erdos minimum overlap problem | Maximize |
| [kernel_builder](#kernel_builder) | Optimize VLIW SIMD kernel for tree traversal | Minimize |
| [kernel_engineering](#kernel_engineering) | Triton kernel for Triangle Multiplicative Update (AlphaFold3) | Maximize |
| [mnist](#mnist) | Handwritten digit classification (accuracy) | Maximize |
| [spaceship_titanic](#spaceship_titanic) | Kaggle: predict passenger transportation (accuracy) | Maximize |
| [stanford_covid_vaccine](#stanford_covid_vaccine) | Predict mRNA degradation rates (MCRMSE) | Minimize |
| [math](#math) | 17 mathematical optimization problems | Maximize |
| [ADRS](#adrs) | 5 systems optimization problems (scheduling, placement, etc.) | Maximize |
| [frontier_cs_algo](#frontier_cs_algo) | 172 algorithmic competition problems (C++) | Maximize |
| [frontier_cs_research](#frontier_cs_research) | 127 research-level CS problems (Python) | Maximize |
| [dna_design](#dna_design) | Design cell-type-specific DNA enhancer sequences (SAGA) | Maximize |
| [drug_design](#drug_design) | Design novel small-molecule antibiotics (SAGA) | Maximize |

## Details

### circle_packing

Pack N=26 circles into a unit square to maximize the sum of radii. The benchmark is 2.635977 (AlphaEvolve result). Score = `sum_radii / 2.635977`.

- **Agents**: 1 (OpenCode runtime)
- **Timeout**: 600s

### erdos

Find a step function h: [0,2] -> [0,1] that minimizes the maximum overlap integral. State-of-the-art bound is 0.380871.

- **Agents**: 1
- **Timeout**: 1100s

### kernel_builder

Optimize instruction scheduling for a VLIW SIMD kernel running tree traversal. The simulator is frozen; only the instruction-building code can be changed. Baseline: 147,734 cycles, best known: 1,363 cycles.

- **Agents**: 1
- **Timeout**: 120s
- **Session**: Docker

### kernel_engineering

Implement a fused Triton kernel for the Triangle Multiplicative Update operation from AlphaFold3 (LayerNorm + projections + gating + einsum). Scored by `1000 / geometric_mean(runtime_us)` across 7 configurations.

- **Agents**: 1
- **Timeout**: 1200s

### mnist

Classify 28x28 handwritten digit images. 60k training / 10k test samples. Scored by accuracy.

- **Agents**: 4
- **Timeout**: 300s

### spaceship_titanic

Kaggle competition: predict which passengers were transported to an alternate dimension. 13 features, binary classification. Top leaderboard accuracy: ~0.828.

- **Agents**: 4
- **Timeout**: 120s

### stanford_covid_vaccine

Predict mRNA degradation rates at each base position. Scored by Mean Columnwise RMSE over three degradation targets.

- **Agents**: 4
- **Timeout**: 300s

### math

17 mathematical optimization problems including circle packing variants, Heilbronn triangle problems, hexagon packing, autocorrelation inequalities, and point placement problems. Each runs 2 agents with a 600s timeout.

### ADRS

5 systems optimization problems:

- **Cloudcast** -- minimize data transfer cost across multi-cloud networks
- **Prism** -- LLM model placement on GPU clusters (minimize KV cache pressure)
- **EPLB** -- expert parallelism load balancing for Mixture-of-Experts
- **LLM-SQL** -- column reordering to maximize LLM prefix cache hits
- **Transaction Scheduling** -- minimize makespan for concurrent transactions

### frontier_cs_algo

172 algorithmic competition problems. Solutions are self-contained C++17 files compiled with `g++ -std=c++17 -O2`. Each is scored 0-100 across 70 test cases.

### frontier_cs_research

127 research-level CS problems with multiple variants (e.g. scheduling under different availability/deadline/overhead configurations). Solutions in Python with 1800s timeouts.

### dna_design

Design 200bp DNA enhancer sequences highly active in HepG2 (liver) cells while minimizing off-target activity. Adapted from the [SAGA](https://github.com/btyu/SAGA) benchmark ([Du et al., 2025](https://arxiv.org/abs/2512.21782)).

- **Agents**: 1
- **Timeout**: 600s
- **Scoring**: GC content + diversity (always); Enformer-based expression prediction (optional)

### drug_design

Design novel small-molecule antibiotics against K. pneumoniae with drug-like properties. Adapted from the [SAGA](https://github.com/btyu/SAGA) benchmark ([Du et al., 2025](https://arxiv.org/abs/2512.21782)).

- **Agents**: 1
- **Timeout**: 600s
- **Scoring**: QED + novelty + PAINS filter (always); MiniMol activity + ChemProp toxicity (optional)

## Writing Your Own

The quickest way to scaffold a new task is `coral init my-task`. To do it manually, create the three pieces:

1. **`seed/`** -- starter code with the function signature your grader will call
2. **`eval/grader.py`** -- a `TaskGrader` subclass that imports and runs the agent's code, then returns a score
3. **`task.yaml`** -- wire them together with the config above

Use `coral validate my-task` to test your grader before launching agents.
