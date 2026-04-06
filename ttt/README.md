# ttt — Test-Time Training for CORAL

This module integrates CORAL with [rLLM](https://github.com/rllm-org/rllm) to enable test-time training (TTT). CORAL is treated as a monolithic agent environment: the RL training loop spawns CORAL agents, collects the LLM call traces they produce, and uses score improvement as the reward signal.

## Architecture

```
rllm AgentTrainer
  │
  ├── trainer.py          Hydra entrypoint, wires config + datasets
  │
  ├── generator.py        Spawns CORAL agents, collects trajectories
  │     │
  │     ├── coral start   First call: launches agents via CLI subprocess
  │     ├── coral resume  Subsequent calls: resumes agents from saved sessions
  │     ├── poll           Waits for N new eval attempts (by commit_hash)
  │     ├── coral stop    Pauses agents, saves sessions for next resume
  │     ├── gateway JSONL  Reads LLM call traces from .coral/public/gateway/requests.jsonl
  │     └── Episode        Returns trajectories + attempt metadata
  │
  └── evaluator.py        Computes reward = score - parent_score
        │
        └── reads parent attempt JSON from .coral/public/attempts/<parent_hash>.json
```

## How it works

### 1. Trainer (`trainer.py`)

The entrypoint. Uses Hydra to load rLLM's unified config and accepts a CORAL `task.yaml` path via `+task_yaml=...`.

- Loads the task YAML and creates a repeated `Dataset` from its `task` section (the dataset is just the same task config repeated — CORAL agents work on the same task across all training steps).
- Sets defaults: `total_epochs=9999` (effectively infinite), `train_batch_size=1`, `val_batch_size=1`.
- Wires the `task_yaml` path into the generator module's `_coral_state` so the generator knows which config to pass to `coral start`.
- Creates an rLLM `AgentTrainer` with the tinker backend, passing the generator and evaluator.

### 2. Generator (`generator.py`)

The generator is an `@rllm.rollout`-decorated function called once per training step. Instead of making direct LLM calls, it orchestrates a full CORAL agent run:

**First call — `coral start`:**
1. Launches `coral start --config task.yaml run.session=local` as a background subprocess.
2. Discovers the `.coral` directory by reading `results_dir` and `task.name` from the YAML, then following the `latest` symlink.
3. Initializes tracking state: `seen_hashes` (set of processed attempt commit hashes), `trace_offset` (line offset into the gateway JSONL).

**Subsequent calls — `coral resume`:**
1. Launches `coral resume --task <slug> run.session=local` as a background subprocess.
2. Agents resume from their saved sessions (Claude Code session IDs persisted in `.coral/public/sessions.json`).

**Every call then:**
1. **Polls for N new evals** — watches `.coral/public/attempts/` for new `<commit_hash>.json` files not in `seen_hashes`. Configurable via `N_EVALS` (default: 1). Polls every 5 seconds with a 600-second timeout.
2. **Stops agents** — runs `coral stop`, which sends SIGTERM to the manager process. This gracefully shuts down agents and saves their sessions for the next resume.
3. **Reads new attempts** — loads the attempt JSON files for the new commit hashes, which contain `score`, `parent_hash`, `agent_id`, `status`, etc.
4. **Collects gateway traces** — reads new lines from `.coral/public/gateway/requests.jsonl` (incremental, starting from `trace_offset`). Each JSONL entry contains a full LLM request/response pair logged by CORAL's gateway middleware.
5. **Converts to rllm Trajectories** — groups JSONL entries by `agent_id`. Each entry becomes an rllm `Step` with `chat_completions` (the request messages + assistant response), `model_response`, and `action` fields. Steps are grouped into `Trajectory` objects (one per agent).
6. **Returns an `Episode`** with the trajectories and metadata (`coral_dir`, `new_commit_hashes`, `new_attempts`).

An `atexit` handler ensures `coral stop` is called if the training process exits unexpectedly.

### 3. Evaluator (`evaluator.py`)

The evaluator is an `@rllm.evaluator`-decorated function that computes the RL reward from CORAL's eval results.

**Reward signal: score improvement over parent commit.**

For the latest attempt in this training step:
1. Reads `score` from the attempt dict.
2. Reads `parent_hash` and looks up the parent attempt's JSON file at `.coral/public/attempts/<parent_hash>.json`.
3. Computes `improvement = score - parent_score`.
4. If no parent exists (first attempt), `parent_score` defaults to 0.

This reward structure incentivizes the agent to make changes that improve the eval score relative to the previous commit, rather than rewarding absolute score (which could lead to reward hacking).

The evaluator assigns the improvement as `traj.reward` on every trajectory in the episode and emits `latest_score` and `improvement` as signals for logging.

## File layout

```
ttt/
  __init__.py       Package marker
  trainer.py        Hydra entrypoint, dataset + config setup
  generator.py      CORAL agent orchestration, trajectory collection
  evaluator.py      Reward computation (score improvement)
  README.md         This file
```

## Usage

```bash
# Install the ttt extra (pulls rllm + tinker)
uv sync --extra ttt

# Run training with a CORAL task config
python -m ttt.trainer +task_yaml=examples/circle_packing/task.yaml

# With overrides
python -m ttt.trainer \
  +task_yaml=examples/circle_packing/task.yaml \
  +repeat=5000 \
  rllm.trainer.total_epochs=100 \
  data.train_batch_size=1
```

## Key configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `+task_yaml` | **required** | Path to a CORAL task YAML config |
| `+repeat` | `1000` | How many times to repeat the task config in the dataset |
| `rllm.trainer.total_epochs` | `9999` | Number of training epochs (effectively infinite) |
| `data.train_batch_size` | `1` | Training batch size (one CORAL run per step) |
| `data.val_batch_size` | `1` | Validation batch size |
| `N_EVALS` | `1` | Number of eval attempts to collect per training step (set in `generator.py`) |

## Data flow

```
task.yaml
  │
  ▼
trainer.py ──► Dataset([task_data] * repeat)
  │
  ▼
generator() is called per training step
  │
  ├─► coral start / coral resume  (background subprocess)
  │     │
  │     ▼
  │   CORAL agents run, make LLM calls through gateway, commit changes, run coral eval
  │     │
  │     ├─► .coral/public/gateway/requests.jsonl     (LLM call traces)
  │     └─► .coral/public/attempts/<hash>.json        (eval results)
  │
  ├─► poll for N new attempt files (by commit_hash)
  ├─► coral stop
  ├─► read gateway JSONL ──► rllm Trajectory/Step objects
  └─► return Episode(trajectories, metadata={coral_dir, new_attempts, ...})
        │
        ▼
evaluator() computes reward
  │
  ├─► attempt.score - parent_attempt.score = improvement
  └─► EvalOutput(reward=improvement)
        │
        ▼
rllm training loop uses reward for RL policy update
```
