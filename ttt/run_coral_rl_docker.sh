#!/bin/bash
# Launch CORAL RL training inside Docker.
#
# Training defaults (GPU counts, learning rate, etc.) live in run_coral_rl.sh.
# This script only sets host paths and forwards caller-set overrides.
#
# Usage:
#   ./ttt/run_coral_rl_docker.sh
#   HF_CKPT=/path/to/model NUM_GPUS=4 ./ttt/run_coral_rl_docker.sh
#   USE_LORA=1 ./ttt/run_coral_rl_docker.sh    # LoRA training with FSDP backend

set -ex

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"

# --- Host paths ---
HF_CKPT="${HF_CKPT:-/path/to/model/weight/Qwen3-30B-A3B-Thinking-2507}"
SAVE_CKPT="${SAVE_CKPT:-${REPO_ROOT}/ttt/ckpt/coral-rl}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/ttt/results}"
mkdir -p "${SAVE_CKPT}" "${RESULTS_DIR}"

# --- Task ---
CORAL_TASK_YAML="${CORAL_TASK_YAML:-/app/ttt/examples/circle_packing/task.yaml}"

DOCKER_ENV=()
DOCKER_ENV+=(-e ROLLOUT_BATCH_SIZE="${ROLLOUT_BATCH_SIZE:-4}")
DOCKER_ENV+=(-e USE_LORA="${USE_LORA:-0}")



# --- Model volume mount: only mount if HF_CKPT is a local path ---
MODEL_ARGS=()
if [[ "${HF_CKPT}" == /* ]]; then
  MODEL_ARGS+=(-v "${HF_CKPT}:/hf_model")
  DOCKER_ENV+=(-e HF_CKPT="/hf_model")
  DOCKER_ENV+=(-e HF_HUB_OFFLINE=1)
else
  # HF model ID — let the container download it
  DOCKER_ENV+=(-e HF_CKPT="${HF_CKPT}")
  DOCKER_ENV+=(-e HF_HUB_OFFLINE=0)
fi

sudo docker run --rm \
  --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 --ulimit nofile=1048576:1048576 \
  --network host \
  "${MODEL_ARGS[@]}" \
  -v "${SAVE_CKPT}:/app/ckpt/coral-rl" \
  -v "${RESULTS_DIR}:/app/results" \
  -v "${REPO_ROOT}/ttt/slime:/app/ttt/slime" \
  -v "${REPO_ROOT}/ttt/coral_rollout.py:/app/ttt/coral_rollout.py:ro" \
  -v "${REPO_ROOT}/ttt/coral_api_server.py:/app/ttt/coral_api_server.py:ro" \
  -v "${REPO_ROOT}/ttt/run_coral_rl.sh:/app/ttt/run_coral_rl.sh:ro" \
  -v "${REPO_ROOT}/ttt/examples:/app/ttt/examples:ro" \
  -e CORAL_TASK_YAML="${CORAL_TASK_YAML}" \
  -e SERVED_MODEL_NAME="qwen3-30b-a3b" \
  "${DOCKER_ENV[@]}" \
  coral-ttt:latest
