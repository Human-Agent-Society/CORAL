# ttt — Test-Time Training for CORAL

This module integrates CORAL with [SLIME](https://github.com/THUDM/slime) (an SGLang-native RL post-training framework) to enable test-time training (TTT) of coding agents. CORAL agents solve tasks while their LLM call traces are intercepted, scored by CORAL's eval system, and fed back as RL reward signals to improve the underlying policy.

The design is inspired by [OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL), which pioneered fully-async RL training of agents from live interaction traces. The key difference is the reward signal: OpenClaw-RL uses a PRM (Process Reward Model) to score each turn, while CORAL TTT uses eval-based outcome reward — the improvement in CORAL eval score between commits.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  SLIME train_async.py  (Megatron actor + SGLang rollout engine) │
│                                                                  │
│  ┌──────────────┐    weight sync     ┌───────────────────┐       │
│  │ Actor (train)│ ◄════════════════► │ SGLang (inference)│       │
│  └──────┬───────┘                    └────────┬──────────┘       │
│         │ reads samples                       │ serves /v1/chat  │
│         ▼                                     ▼                  │
│  ┌─────────────────────────────────────────────────────┐         │
│  │  CoralAPIServer  (FastAPI proxy, :30000)             │         │
│  │  - forwards requests to SGLang                      │         │
│  │  - extracts per-token logprobs                      │         │
│  │  - creates SLIME Sample objects                     │         │
│  │  - buffers samples per-agent until eval score       │         │
│  │  - assigns reward = score_improvement on eval       │         │
│  │  - submits scored samples to SLIME data buffer      │         │
│  └──────────────────────────┬──────────────────────────┘         │
└─────────────────────────────┼────────────────────────────────────┘
                              │ OpenAI-compat API
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  CORAL  (agent orchestration)                                    │
│                                                                  │
│  ┌──────────────┐   litellm    ┌────────────┐   eval    ┌─────┐ │
│  │ Coding Agent │ ──gateway──► │ API Server │ ◄──────── │Eval │ │
│  │ (opencode)   │              │ (logprobs) │           │Score│ │
│  └──────────────┘              └────────────┘           └─────┘ │
│        │                                                         │
│        └──► git commit ──► coral eval ──► .coral/attempts/*.json │
└──────────────────────────────────────────────────────────────────┘
```

## How it works

### 1. CoralAPIServer (`coral_api_server.py`)

A FastAPI proxy that sits between CORAL's litellm gateway and SGLang. For every chat completion request:

1. Forwards the request to SGLang with `logprobs=True`.
2. Extracts per-token log-probabilities from the response.
3. Tokenizes the prompt and response using the model's chat template.
4. Creates a SLIME `Sample` with `prompt`, `response`, `tokens`, `rollout_log_probs`, and `loss_mask`.
5. Buffers the sample under the originating agent's ID (resolved via `X-Coral-Agent-Id` header or gateway log fingerprinting).
6. When `report_eval_score()` is called (by the eval monitor), assigns `reward = score - parent_score` to all buffered samples for that agent and submits them to SLIME's data buffer.

Supports both streaming and non-streaming requests. Samples with zero improvement get `loss_mask = [0, ...]` so the policy doesn't train on no-change commits.

### 2. Rollout Worker (`coral_rollout.py`)

Bridges CoralAPIServer with SLIME's training loop via the `generate_rollout_coral()` function (registered as SLIME's rollout function).

- **`AsyncRolloutWorker`** — manages the CoralAPIServer instance, CORAL agent subprocess, and an eval monitor thread.
- **Eval monitor** — polls `.coral/public/attempts/` for new eval results, computes `improvement = score - parent_score`, and calls `report_eval_score()` on the API server to assign rewards.
- **Pause/resume** — submission is paused during weight updates (SLIME sync) and resumed when the new policy is loaded.
- **Drain loop** — `_drain_output_queue()` waits until `rollout_batch_size` scored samples are collected before returning them to SLIME for the training step.

### 3. Training script (`run_coral_rl.sh`)

Orchestrates the full training run:

1. Auto-detects model architecture from HF checkpoint config and sources the corresponding SLIME model script.
2. Starts Ray head node for distributed training.
3. Launches `train_async.py` with actor GPUs (Megatron training) and rollout GPUs (SGLang inference).
4. Supports full-parameter training (Megatron backend with tensor/sequence/context parallelism) and LoRA training (FSDP backend).
5. GRPO advantage estimation with KL loss, configurable clip ranges, and optional W&B logging.

### Reward signal

**Outcome-based reward via eval score improvement.**

When a CORAL agent commits code and runs `coral eval`, the eval monitor:
1. Reads the new attempt's `score` from `.coral/public/attempts/<hash>.json`.
2. Reads the parent attempt's score via `parent_hash`.
3. Computes `improvement = score - parent_score`.
4. Assigns improvement as reward to all LLM call traces (samples) generated by that agent since the last eval.

This incentivizes changes that improve eval scores relative to the previous commit, avoiding reward hacking from absolute scores.

## File layout

```
ttt/
  coral_api_server.py   FastAPI proxy: SGLang forwarding, logprob extraction, sample creation
  coral_rollout.py      SLIME rollout function: agent lifecycle, eval monitoring, reward assignment
  run_coral_rl.sh       Training launcher: Ray, SLIME train_async.py, model/GPU config
  run_coral_rl_docker.sh  Docker wrapper for run_coral_rl.sh
  docker/
    Dockerfile          Builds on SLIME base image, adds CORAL + opencode
    entrypoint.sh       Container entrypoint
  slime/                SLIME framework (vendored, see acknowledgments)
  examples/
    circle_packing/     Example task: pack 26 circles into a unit square
  README.md             This file
```

## Usage

### Bare metal

```bash
# Set your task config
export CORAL_TASK_YAML=ttt/examples/circle_packing/task.yaml

# Full-parameter training (8 GPUs: 4 actor + 4 rollout)
./ttt/run_coral_rl.sh

# Customize GPU allocation and model
NUM_GPUS=4 ACTOR_GPUS=2 ROLLOUT_GPUS=2 \
  HF_CKPT=Qwen/Qwen3-30B-A3B-Thinking-2507 \
  ./ttt/run_coral_rl.sh

# LoRA training (FSDP backend)
USE_LORA=1 ./ttt/run_coral_rl.sh
```

### Docker

```bash
# Build (from repo root)
docker build -t coral-ttt -f ttt/docker/Dockerfile .

# Run
CORAL_TASK_YAML=/app/ttt/examples/circle_packing/task.yaml \
  ./ttt/run_coral_rl_docker.sh

# With custom model and LoRA
HF_CKPT=/path/to/model USE_LORA=1 ./ttt/run_coral_rl_docker.sh
```

## Key configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CORAL_TASK_YAML` | **required** | Path to CORAL task YAML config |
| `NUM_GPUS` | `8` | Total GPUs available |
| `ACTOR_GPUS` | `4` | GPUs for Megatron actor (training) |
| `ROLLOUT_GPUS` | `4` | GPUs for SGLang rollout (inference) |
| `HF_CKPT` | `Qwen/Qwen3-30B-A3B-Thinking-2507` | HuggingFace model checkpoint |
| `USE_LORA` | `0` | Set to `1` for LoRA training with FSDP backend |
| `ROLLOUT_BATCH_SIZE` | `16` (`4` in Docker) | Samples to collect per training step |
| `LR` | `1e-5` | Learning rate |
| `KL_LOSS_COEF` | `0.0` | KL divergence loss coefficient |
| `USE_WANDB` | `0` | Set to `1` to enable W&B logging |
| `WANDB_PROJECT` | `coral_rl` | W&B project name |
| `CONTEXT_LENGTH` | `131072` | Maximum context length for SGLang |

## Acknowledgments

This module builds on two external projects:

- **[SLIME](https://github.com/THUDM/slime)** — the SGLang-native RL post-training framework that provides the training loop (Megatron actor + SGLang rollout), data buffer, and async training infrastructure. Vendored under `ttt/slime/`. Licensed under Apache 2.0.

- **[OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)** — the fully-async agent RL framework whose architecture (intercept agent LLM calls, collect logprobs, train in background) inspired the CoralAPIServer design. The key adaptation is replacing OpenClaw-RL's PRM-based per-turn scoring with CORAL's eval-based outcome reward.
