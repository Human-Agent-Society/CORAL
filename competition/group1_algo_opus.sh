#!/bin/bash
# Group 1: Algo problems, Claude Code Opus
# Problems: algo 0-15 (15 problems), 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group1_algo_opus"
RUNTIME="claude_code"
MODEL="claude-opus-4-6"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_algo/0"
    "$CORAL_ROOT/examples/frontier_cs_algo/1"
    "$CORAL_ROOT/examples/frontier_cs_algo/2"
    "$CORAL_ROOT/examples/frontier_cs_algo/3"
    "$CORAL_ROOT/examples/frontier_cs_algo/4"
    "$CORAL_ROOT/examples/frontier_cs_algo/5"
    "$CORAL_ROOT/examples/frontier_cs_algo/6"
    "$CORAL_ROOT/examples/frontier_cs_algo/7"
    "$CORAL_ROOT/examples/frontier_cs_algo/8"
    "$CORAL_ROOT/examples/frontier_cs_algo/9"
    "$CORAL_ROOT/examples/frontier_cs_algo/10"
    "$CORAL_ROOT/examples/frontier_cs_algo/11"
    "$CORAL_ROOT/examples/frontier_cs_algo/13"
    "$CORAL_ROOT/examples/frontier_cs_algo/14"
    "$CORAL_ROOT/examples/frontier_cs_algo/15"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
