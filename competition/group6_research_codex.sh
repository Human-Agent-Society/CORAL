#!/bin/bash
# Group 6: Research problems, Codex GPT-5.4
# 15 fuzzing/regression/LLM problems, 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group6_research_codex"
RUNTIME="codex"
MODEL="gpt-5.4"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_research/grammar_fuzzing__fuzzer_sql"
    "$CORAL_ROOT/examples/frontier_cs_research/grammar_fuzzing__seed_sql"
    "$CORAL_ROOT/examples/frontier_cs_research/llm_router"
    "$CORAL_ROOT/examples/frontier_cs_research/llm_sql__large"
    "$CORAL_ROOT/examples/frontier_cs_research/llm_sql__small"
    "$CORAL_ROOT/examples/frontier_cs_research/mamba2_scan"
    "$CORAL_ROOT/examples/frontier_cs_research/qknorm"
    "$CORAL_ROOT/examples/frontier_cs_research/quant_dot_int4"
    "$CORAL_ROOT/examples/frontier_cs_research/ragged_attention"
    "$CORAL_ROOT/examples/frontier_cs_research/symbolic_regression__mccormick"
    "$CORAL_ROOT/examples/frontier_cs_research/symbolic_regression__mixed_polyexp_4d"
    "$CORAL_ROOT/examples/frontier_cs_research/symbolic_regression__peaks"
    "$CORAL_ROOT/examples/frontier_cs_research/symbolic_regression__ripple"
    "$CORAL_ROOT/examples/frontier_cs_research/symbolic_regression__sincos"
    "$CORAL_ROOT/examples/frontier_cs_research/vector_addition__2_24"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
