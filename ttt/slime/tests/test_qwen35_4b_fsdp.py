"""
Qwen3.5-4B multimodal FSDP integration test.
Validates the full multimodal training pipeline using the geo3k geometry dataset (image + text).

Prerequisites:
    1. 4 GPUs (A100/A800/H100, >=24GB VRAM each)
    2. geo3k_imgurl dataset available locally

Environment variables:
    SLIME_TEST_MODEL_PATH   Path to Qwen3.5-4B model (required)
    SLIME_TEST_DATASET_DIR  Path to geo3k_imgurl dataset directory (required)
    SLIME_TEST_NUM_GPUS     Number of GPUs (default: 4)
    SLIME_TEST_ENABLE_EVAL  Enable eval during training (default: 1)

Usage:
    cd <slime_dir>
    SLIME_TEST_MODEL_PATH=/path/to/Qwen3.5-4B \\
    SLIME_TEST_DATASET_DIR=/path/to/geo3k_imgurl \\
    python tests/test_qwen35_4b_fsdp.py

Validation coverage:
    - AutoModelForImageTextToText loading (vision_config auto-detection)
    - AutoProcessor loading (patch_size=16, merge=2)
    - SGLang engine startup + patch_sglang_qwen35() auto-triggered
    - Multimodal data processing (image URL -> PIL Image -> processor -> pixel_values)
    - GRPO training forward/backward (FSDP + gradient checkpointing)
    - Math reward function (rm-type math)
"""
import os

import slime.utils.external_utils.command_utils as U

ENABLE_EVAL = bool(int(os.environ.get("SLIME_TEST_ENABLE_EVAL", "1")))
NUM_GPUS = int(os.environ.get("SLIME_TEST_NUM_GPUS", "4"))

MODEL_PATH = os.environ.get("SLIME_TEST_MODEL_PATH")
DATASET_DIR = os.environ.get("SLIME_TEST_DATASET_DIR")


def prepare():
    if not MODEL_PATH:
        raise RuntimeError("Set SLIME_TEST_MODEL_PATH to the Qwen3.5-4B model directory")
    if not DATASET_DIR:
        raise RuntimeError("Set SLIME_TEST_DATASET_DIR to the geo3k_imgurl dataset directory")
    if not os.path.isdir(DATASET_DIR):
        raise RuntimeError(f"Dataset directory not found: {DATASET_DIR}")


def execute():
    ckpt_args = f"--hf-checkpoint {MODEL_PATH} "

    rollout_args = (
        f"--prompt-data {DATASET_DIR}/train.parquet "
        "--input-key problem "
        "--label-key answer "
        "--apply-chat-template "
        "--rollout-shuffle "
        "--rm-type math "
        "--num-rollout 3 "
        "--rollout-batch-size 8 "
        "--n-samples-per-prompt 8 "
        "--rollout-max-response-len 2048 "
        "--rollout-temperature 1 "
        "--global-batch-size 4 "
    )

    multimodal_args = '--multimodal-keys \'{"image": "images"}\' '

    eval_args = (
        f"{'--eval-interval 20 ' if ENABLE_EVAL else ''}"
        f"--eval-prompt-data geo3k {DATASET_DIR}/test.parquet "
        "--n-samples-per-eval-prompt 1 "
        "--eval-max-response-len 2048 "
    )

    fsdp_args = (
        "--train-backend fsdp "
        "--gradient-checkpointing "
        "--update-weight-buffer-size 536870912 "
        "--attn-implementation eager "
    )

    grpo_args = (
        "--advantage-estimator grpo "
        "--kl-loss-coef 0.00 "
        "--kl-loss-type low_var_kl "
        "--kl-coef 0.00 "
        "--entropy-coef 0.00 "
        "--eps-clip 0.2 "
        "--eps-clip-high 0.28 "
    )

    optimizer_args = (
        "--optimizer adam "
        "--lr 1e-6 "
        "--lr-decay-style constant "
        "--weight-decay 0.1 "
        "--adam-beta1 0.9 "
        "--adam-beta2 0.98 "
    )

    sglang_args = (
        "--rollout-num-gpus-per-engine 1 "
        "--sglang-mem-fraction-static 0.4 "
        "--sglang-decode-log-interval 1000 "
        "--sglang-enable-metrics "
    )

    ci_args = "--ci-test "

    misc_args = (
        "--actor-num-nodes 1 "
        f"--actor-num-gpus-per-node {NUM_GPUS} "
        "--colocate "
    )

    train_args = (
        f"{ckpt_args} "
        f"{rollout_args} "
        f"{multimodal_args} "
        f"{optimizer_args} "
        f"{grpo_args} "
        f"{U.get_default_wandb_args(__file__)} "
        f"{fsdp_args} "
        f"{eval_args} "
        f"{sglang_args} "
        f"{ci_args} "
        f"{misc_args} "
    )

    extra_env_vars = {
        "CUDA_DEVICE_MAX_CONNECTIONS": "1",
    }

    U.execute_train(
        train_args=train_args,
        num_gpus_per_node=NUM_GPUS,
        megatron_model_type=None,
        extra_env_vars=extra_env_vars,
    )


if __name__ == "__main__":
    prepare()
    for proxy_var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(proxy_var, None)
    execute()
