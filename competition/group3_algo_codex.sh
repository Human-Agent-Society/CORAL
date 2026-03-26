#!/bin/bash
# Group 3: Algo problems, Codex GPT-5.4
# Problems: algo 42-60 (15 problems), 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group3_algo_codex"
RUNTIME="codex"
MODEL="gpt-5.4"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_algo/42"
    "$CORAL_ROOT/examples/frontier_cs_algo/43"
    "$CORAL_ROOT/examples/frontier_cs_algo/44"
    "$CORAL_ROOT/examples/frontier_cs_algo/45"
    "$CORAL_ROOT/examples/frontier_cs_algo/46"
    "$CORAL_ROOT/examples/frontier_cs_algo/47"
    "$CORAL_ROOT/examples/frontier_cs_algo/48"
    "$CORAL_ROOT/examples/frontier_cs_algo/50"
    "$CORAL_ROOT/examples/frontier_cs_algo/52"
    "$CORAL_ROOT/examples/frontier_cs_algo/53"
    "$CORAL_ROOT/examples/frontier_cs_algo/54"
    "$CORAL_ROOT/examples/frontier_cs_algo/57"
    "$CORAL_ROOT/examples/frontier_cs_algo/58"
    "$CORAL_ROOT/examples/frontier_cs_algo/59"
    "$CORAL_ROOT/examples/frontier_cs_algo/60"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
