#!/bin/bash
# Group 4: Research problems, Claude Code Opus
# 15 GPU/kernel problems, 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group4_research_opus"
RUNTIME="claude_code"
MODEL="claude-opus-4-6"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_research/cloudcast"
    "$CORAL_ROOT/examples/frontier_cs_research/cross_entropy"
    "$CORAL_ROOT/examples/frontier_cs_research/decoding_attn"
    "$CORAL_ROOT/examples/frontier_cs_research/flash_attn"
    "$CORAL_ROOT/examples/frontier_cs_research/fused_linear_ce"
    "$CORAL_ROOT/examples/frontier_cs_research/fused_linear_jsd"
    "$CORAL_ROOT/examples/frontier_cs_research/gdpa_attention"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__annoying"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__k_skewed"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__near_tile"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__rectangles"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__squares"
    "$CORAL_ROOT/examples/frontier_cs_research/gemm_optimization__transformerish"
    "$CORAL_ROOT/examples/frontier_cs_research/group_gemm"
    "$CORAL_ROOT/examples/frontier_cs_research/mixed_gemm"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
