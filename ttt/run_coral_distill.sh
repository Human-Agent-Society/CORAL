#!/bin/bash
# CORAL Self-Distillation training with SLIME.
#
# Instead of RL (GRPO), this uses SFT on successful trajectories.
# Failed attempts trigger agent self-reflection via CORAL's heartbeat;
# if the agent recovers, the reflection + corrected trajectory become SFT data.
#
# Usage:
#   CORAL_TASK_YAML=examples/circle_packing/task.yaml ./ttt/run_coral_distill.sh
#   NUM_GPUS=4 ACTOR_GPUS=2 ROLLOUT_GPUS=2 HF_CKPT=/path/to/model ./ttt/run_coral_distill.sh
#   USE_LORA=1 ./ttt/run_coral_distill.sh

set -ex

export PYTHONUNBUFFERED=1
export PYTHONFAULTHANDLER=1

# --- Paths ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
SLIME_ROOT="${SLIME_ROOT:-${SCRIPT_DIR}/slime}"
MEGATRON_ROOT="${MEGATRON_ROOT:-}"

# --- Task config (required) ---
if [ -z "${CORAL_TASK_YAML:-}" ]; then
    echo "ERROR: CORAL_TASK_YAML must be set to the path of your task.yaml"
    exit 1
fi
export CORAL_TASK_YAML

# --- GPU allocation ---
NUM_GPUS=${NUM_GPUS:-8}
ACTOR_GPUS=${ACTOR_GPUS:-4}
ROLLOUT_GPUS=${ROLLOUT_GPUS:-4}

if (( ACTOR_GPUS + ROLLOUT_GPUS > NUM_GPUS )); then
    echo "ACTOR_GPUS + ROLLOUT_GPUS must be <= NUM_GPUS"
    exit 1
fi

# --- Ray health checks ---
export RAY_health_check_failure_threshold=20
export RAY_health_check_period_ms=5000
export RAY_health_check_timeout_ms=30000
export RAY_num_heartbeats_timeout=60

# --- Model ---
HF_CKPT=${HF_CKPT:-"Qwen/Qwen3-30B-A3B-Thinking-2507"}
REF_LOAD=${REF_LOAD:-${HF_CKPT}}
SAVE_CKPT=${SAVE_CKPT:-"${REPO_ROOT}/ckpt/coral-distill"}

# --- Distillation config ---
# Minimum score for a trajectory to be kept as SFT data (0.0 = any non-zero)
export DISTILL_MIN_SCORE=${DISTILL_MIN_SCORE:-0.0}

# --- SGLang ---
TP=${TP:-4}
CP=${CP:-1}
CONTEXT_LENGTH=${CONTEXT_LENGTH:-131072}
MEM_FRACTION_STATIC=${MEM_FRACTION_STATIC:-0.85}
REASONING_PARSER=${REASONING_PARSER:-qwen3}
TOOL_CALL_PARSER=${TOOL_CALL_PARSER:-qwen}

# --- API server ---
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-"qwen3-30b-a3b"}
export HOST="0.0.0.0"
export PORT="${PORT:-30000}"
export SERVED_MODEL_NAME

# --- Record (session logging) ---
export CORAL_RECORD_ENABLED="${CORAL_RECORD_ENABLED:-1}"
export CORAL_RECORD_FILE="${CORAL_RECORD_FILE:-${REPO_ROOT}/results/coral_distill_record.jsonl}"

# --- Source model config for architecture flags ---
_model_type=""
_lower_ckpt=$(echo "${HF_CKPT}" | tr '[:upper:]' '[:lower:]')
case "${_lower_ckpt}" in
  *qwen3.5*) _model_type="qwen3_5" ;;
  *qwen3*moe*|*qwen3*a3b*|*qwen3*a22b*|*qwen3*a32b*|*qwen3*a12b*) _model_type="qwen3_moe" ;;
  *qwen3*) _model_type="qwen3" ;;
  *qwen2*) _model_type="qwen2" ;;
  *llama*) _model_type="llama" ;;
  *glm*moe*|*glm*a12b*|*glm*a32b*) _model_type="glm_moe" ;;
  *glm*) _model_type="glm" ;;
  *moonlight*|*kimi*k2*) _model_type="qwen3_moe" ;;
  *mimo*) _model_type="mimo" ;;
  *deepseek*v3*|*deepseek*r2*) _model_type="deepseek_v3" ;;
esac

MODEL_ARGS=()
if [ -n "${_model_type}" ]; then
  _config_script="${SLIME_ROOT}/scripts/models/${_model_type}.sh"
  if [ -f "${_config_script}" ]; then
    source "${_config_script}"
  fi
fi

# --- Checkpoint ---
CKPT_ARGS=(
   --hf-checkpoint "${HF_CKPT}"
   --ref-load "${REF_LOAD}"
   --save-checkpoint "${SAVE_CKPT}"
   --save-interval 10
)
if [ "${USE_LORA}" != "1" ]; then
   CKPT_ARGS+=(--megatron-to-hf-mode bridge)
fi

# --- Rollout (self-distillation instead of RL) ---
ROLLOUT_ARGS=(
   --disable-rollout-global-dataset
   --rollout-function-path coral_distill.generate_distill_data

   --num-rollout 100000000
   --rollout-batch-size "${ROLLOUT_BATCH_SIZE:-16}"
   --n-samples-per-prompt 1
   --rollout-max-response-len 32768
   --rollout-max-context-len "${CONTEXT_LENGTH}"
   --rollout-temperature "${ROLLOUT_TEMPERATURE:-0.6}"
   --reward-key score

   --num-steps-per-rollout 1
)

# --- Backend ---
if [ "${USE_LORA}" = "1" ]; then
  BACKEND_ARGS=(--train-backend fsdp)
  MODEL_ARGS=()
  PERF_ARGS=(
     --use-dynamic-batch-size
     --max-tokens-per-gpu "${MAX_TOKENS_PER_GPU:-8192}"
     --gradient-checkpointing
  )
  LORA_ARGS=(
     --use-lora
     --lora-rank "${LORA_RANK:-16}"
     --lora-alpha "${LORA_ALPHA:-32}"
     --lora-target-modules "${LORA_TARGET_MODULES:-q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj}"
  )
else
  BACKEND_ARGS=()
  PERF_ARGS=(
     --tensor-model-parallel-size "${TP}"
     --sequence-parallel
     --pipeline-model-parallel-size 1
     --context-parallel-size "${CP}"
     --expert-model-parallel-size 1
     --expert-tensor-parallel-size 1

     --recompute-granularity full
     --recompute-method uniform
     --recompute-num-layers 1

     --use-dynamic-batch-size
     --max-tokens-per-gpu "${MAX_TOKENS_PER_GPU:-98304}"
     --log-probs-chunk-size 1024
  )
  LORA_ARGS=()
fi

# --- SFT loss (replaces GRPO) ---
# Use KL loss to prevent drift from the reference model.
# No policy gradient, no clipping, no advantage estimation.
SFT_ARGS=(
   --advantage-estimator grpo
   --disable-rewards-normalization
   --use-kl-loss
   --kl-loss-coef "${KL_LOSS_COEF:-0.01}"
   --kl-loss-type low_var_kl
   --entropy-coef 0.00
   --eps-clip 1000.0
   --eps-clip-high 1000.0
)
# NOTE: eps-clip is set very high (1000) to effectively disable clipping.
# With SFT data (all rewards positive, loss_mask=1 for good trajectories),
# the loss reduces to standard cross-entropy + KL regularization.
# SLIME doesn't have a native SFT mode in train_async, so we use GRPO
# with no clipping as the closest equivalent.

# --- Optimizer ---
OPTIMIZER_ARGS=(
   --optimizer adam
   --lr "${LR:-5e-6}"
   --lr-decay-style constant
   --weight-decay 0.1
   --adam-beta1 0.9
   --adam-beta2 0.98
)
if [ "${USE_LORA}" != "1" ]; then
   OPTIMIZER_ARGS+=(
      --optimizer-cpu-offload
      --overlap-cpu-optimizer-d2h-h2d
      --use-precision-aware-optimizer
   )
fi

# --- SGLang ---
SGLANG_ARGS=(
   --rollout-num-gpus-per-engine "${ROLLOUT_GPUS}"
   --sglang-tool-call-parser "${TOOL_CALL_PARSER}"
   --sglang-mem-fraction-static "${MEM_FRACTION_STATIC}"
   --sglang-context-length "${CONTEXT_LENGTH}"
   --sglang-reasoning-parser "${REASONING_PARSER}"
   --sglang-moe-runner-backend triton_kernel
)

CUSTOM_ARGS=(
   --custom-generate-function-path coral_api_server.generate
   --custom-rm-path coral_api_server.reward_func
)

if [ "${USE_LORA}" != "1" ]; then
  MISC_ARGS=(
     --attention-dropout 0.0
     --hidden-dropout 0.0
     --accumulate-allreduce-grads-in-fp32
     --attention-softmax-in-fp32
     --attention-backend flash
  )
else
  MISC_ARGS=()
fi

# --- Wandb ---
USE_WANDB=${USE_WANDB:-0}
WANDB_PROJECT=${WANDB_PROJECT:-coral_distill}
WANDB_KEY_VALUE=${WANDB_KEY:-${WANDB_API_KEY:-}}
if [ "${USE_WANDB}" = "1" ] && [ -n "${WANDB_KEY_VALUE}" ]; then
  WANDB_ARGS=(
    --use-wandb
    --wandb-project "${WANDB_PROJECT}"
    --wandb-group coral-distill
    --wandb-key "${WANDB_KEY_VALUE}"
  )
else
  WANDB_ARGS=()
fi

# --- Launch Ray ---
export MASTER_ADDR=${MASTER_ADDR:-"127.0.0.1"}
export no_proxy="127.0.0.1,${MASTER_ADDR}"
for _attempt in 1 2 3 4 5; do
    if ray start --head --node-ip-address "${MASTER_ADDR}" --num-gpus "${NUM_GPUS}" \
        --disable-usage-stats --dashboard-host=0.0.0.0 --dashboard-port=8265; then
        break
    fi
    echo "Ray start attempt ${_attempt} failed, retrying..."
    ray stop --force 2>/dev/null || true
    sleep 1
done

export PYTHONPATH="${SCRIPT_DIR}:${SLIME_ROOT}${MEGATRON_ROOT:+:${MEGATRON_ROOT}}:${PYTHONPATH:-}"
export CUDA_DEVICE_MAX_CONNECTIONS=1

python3 "${SLIME_ROOT}/train_async.py" \
   "${BACKEND_ARGS[@]}" \
   --actor-num-nodes 1 \
   --actor-num-gpus-per-node "${ACTOR_GPUS}" \
   --rollout-num-gpus "${ROLLOUT_GPUS}" \
   --num-gpus-per-node "${NUM_GPUS}" \
   "${MODEL_ARGS[@]}" \
   "${CKPT_ARGS[@]}" \
   "${ROLLOUT_ARGS[@]}" \
   "${OPTIMIZER_ARGS[@]}" \
   "${SFT_ARGS[@]}" \
   "${PERF_ARGS[@]}" \
   "${SGLANG_ARGS[@]}" \
   "${MISC_ARGS[@]}" \
   "${WANDB_ARGS[@]}" \
   "${CUSTOM_ARGS[@]}" \
   "${LORA_ARGS[@]}"
