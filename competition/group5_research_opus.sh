#!/bin/bash
# Group 5: Research problems, Claude Code Opus
# 15 ML/sim/scheduling problems, 2 problems at a time, 1 agent each
source "$(dirname "$0")/common.sh"

GROUP_NAME="group5_research_opus"
RUNTIME="claude_code"
MODEL="claude-opus-4-6"

PROBLEMS=(
    "$CORAL_ROOT/examples/frontier_cs_research/cant_be_late__high_availability_loose_deadline_large_overhead"
    "$CORAL_ROOT/examples/frontier_cs_research/cant_be_late__high_availability_tight_deadline_large_overhead"
    "$CORAL_ROOT/examples/frontier_cs_research/cant_be_late__low_availability_loose_deadline_large_overhead"
    "$CORAL_ROOT/examples/frontier_cs_research/cant_be_late_multi__high_availability_loose_deadline_large_overhead"
    "$CORAL_ROOT/examples/frontier_cs_research/cant_be_late_multi__low_availability_tight_deadline_small_overhead"
    "$CORAL_ROOT/examples/frontier_cs_research/imagenet_pareto__200k"
    "$CORAL_ROOT/examples/frontier_cs_research/imagenet_pareto__500k"
    "$CORAL_ROOT/examples/frontier_cs_research/imagenet_pareto__1m"
    "$CORAL_ROOT/examples/frontier_cs_research/imagenet_pareto__2_5m"
    "$CORAL_ROOT/examples/frontier_cs_research/imagenet_pareto__5m"
    "$CORAL_ROOT/examples/frontier_cs_research/nbody_simulation__random_10k"
    "$CORAL_ROOT/examples/frontier_cs_research/nbody_simulation__random_100k"
    "$CORAL_ROOT/examples/frontier_cs_research/vdb_pareto__balanced"
    "$CORAL_ROOT/examples/frontier_cs_research/vdb_pareto__high_recall"
    "$CORAL_ROOT/examples/frontier_cs_research/vdb_pareto__low_latency"
)

CSV=$(init_csv "$GROUP_NAME")
echo "=== $GROUP_NAME: ${#PROBLEMS[@]} problems, $RUNTIME $MODEL ==="

run_group "$CSV" "$RUNTIME" "$MODEL" "${PROBLEMS[@]}"
print_summary "$CSV" "$GROUP_NAME"
