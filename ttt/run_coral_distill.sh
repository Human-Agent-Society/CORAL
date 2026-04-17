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
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

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
# IMPORTANT: Your task.yaml should include the 'diagnose' heartbeat action
# for self-distillation to capture rationales:
#   agents:
#     heartbeat:
#       - name: reflect
#         every: 1
#       - name: diagnose
#         every: 1
#       - name: consolidate
#         every: 10
#         global: true
#       - name: pivot
#         every: 5
#         trigger: plateau
export DISTILL_MIN_SCORE=${DISTILL_MIN_SCORE:-0.0}

# --- SGLang / parallelism ---
TP=${TP:-4}
CP=${CP:-1}
EP=${EP:-1}
ETP=${ETP:-1}
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

# --- Auto-detect model config ---
# Auto-detect rotary_base from model config if not explicitly set.
if [ -z "${MODEL_ARGS_ROTARY_BASE:-}" ] && [ -f "${HF_CKPT}/config.json" ]; then
    _rope_theta=$(python3 -c "import json; print(int(json.load(open('${HF_CKPT}/config.json')).get('rope_theta', 0)))" 2>/dev/null || true)
    if [ -n "${_rope_theta}" ] && [ "${_rope_theta}" != "0" ]; then
        export MODEL_ARGS_ROTARY_BASE="${_rope_theta}"
        echo "Auto-detected rotary_base=${MODEL_ARGS_ROTARY_BASE} from model config"
    fi
fi

# Source model config script. Set MODEL_SCRIPT to override auto-detection.
if [ -z "${MODEL_SCRIPT:-}" ]; then
    _model_type=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('${HF_CKPT}/config.json'))
    mt = cfg.get('model_type', '')
    ne = cfg.get('num_experts', 0) or 0
    nh = cfg.get('num_hidden_layers', 0)
    hs = cfg.get('hidden_size', 0)
    print(f'{mt}:{ne}:{nh}:{hs}')
except Exception:
    print('unknown:0:0:0')
" 2>/dev/null || echo "unknown:0:0:0")
    IFS=: read -r _mt _ne _nh _hs <<< "${_model_type}"
    case "${_mt}" in
        qwen3_moe)   MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-30B-A3B.sh" ;;
        qwen3)
            if [ "${_nh}" = "64" ]; then
                MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-32B.sh"
            elif [ "${_hs}" = "5120" ]; then
                MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-14B.sh"
            elif [ "${_hs}" = "4096" ]; then
                MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-8B.sh"
            elif [ "${_hs}" = "2560" ]; then
                MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-4B.sh"
            else
                MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-4B.sh"
            fi
            ;;
        *)           MODEL_SCRIPT="${SLIME_ROOT}/scripts/models/qwen3-30B-A3B.sh" ;;
    esac
fi

MODEL_ARGS=()
if [ -f "${MODEL_SCRIPT}" ]; then
    echo "Sourcing model config: ${MODEL_SCRIPT}"
    source "${MODEL_SCRIPT}"
else
    echo "WARNING: Model script not found: ${MODEL_SCRIPT}"
fi

# --- Checkpoint ---
CKPT_ARGS=(
   --hf-checkpoint "${HF_CKPT}"
   --ref-load "${REF_LOAD}"
   --save "${SAVE_CKPT}"
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
     --expert-model-parallel-size "${EP}"
     --expert-tensor-parallel-size "${ETP}"
     --use-distributed-optimizer

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
     --bf16
     --attention-dropout 0.0
     --hidden-dropout 0.0
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
