#!/bin/bash
# Group 2: Algo problems, Claude Code Opus
# Problems: algo 16-41 (15 problems), 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group2_algo_opus"
RUNTIME="claude_code"
MODEL="claude-opus-4-6"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_algo/16"
    "$CORAL_ROOT/examples/frontier_cs_algo/17"
    "$CORAL_ROOT/examples/frontier_cs_algo/22"
    "$CORAL_ROOT/examples/frontier_cs_algo/23"
    "$CORAL_ROOT/examples/frontier_cs_algo/24"
    "$CORAL_ROOT/examples/frontier_cs_algo/25"
    "$CORAL_ROOT/examples/frontier_cs_algo/26"
    "$CORAL_ROOT/examples/frontier_cs_algo/27"
    "$CORAL_ROOT/examples/frontier_cs_algo/28"
    "$CORAL_ROOT/examples/frontier_cs_algo/30"
    "$CORAL_ROOT/examples/frontier_cs_algo/33"
    "$CORAL_ROOT/examples/frontier_cs_algo/35"
    "$CORAL_ROOT/examples/frontier_cs_algo/36"
    "$CORAL_ROOT/examples/frontier_cs_algo/40"
    "$CORAL_ROOT/examples/frontier_cs_algo/41"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
