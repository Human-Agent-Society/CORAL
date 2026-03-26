#!/bin/bash
# Common functions for competition runners
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORAL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMEOUT_SECONDS=$((90 * 60))  # 1.5 hours per problem
PARALLEL=2                     # run 2 problems concurrently

# Initialize CSV for a group
# Usage: init_csv <group_name>
init_csv() {
    local group_name="$1"
    local csv="$RESULTS_DIR/${group_name}.csv"
    if [ ! -f "$csv" ]; then
        echo "problem_id,problem_path,command,result_dir,best_score,sota_score,gap_to_sota,status" > "$csv"
    fi
    echo "$csv"
}

# Extract best score from .coral/public/attempts/*.json
# Usage: extract_best_score <coral_dir>
extract_best_score() {
    local coral_dir="$1"
    local attempts_dir="$coral_dir/public/attempts"
    if [ ! -d "$attempts_dir" ]; then
        echo "0"
        return
    fi
    python3 -c "
import json, glob, sys
best = 0.0
for f in glob.glob('${attempts_dir}/*.json'):
    try:
        data = json.load(open(f))
        score = data.get('score')
        if score is not None and float(score) > best:
            best = float(score)
    except:
        pass
print(f'{best:.4f}')
"
}

# Collect result for a finished problem and append to CSV
# Usage: collect_result <csv_file> <problem_path> <cmd>
collect_result() {
    local csv_file="$1"
    local problem_path="$2"
    local cmd="$3"
    local problem_id
    problem_id=$(basename "$problem_path")
    local task_yaml="$problem_path/task.yaml"

    # Find the result directory via task name slug
    local task_name
    task_name=$(python3 -c "
import yaml
with open('${task_yaml}') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('task', {}).get('name', ''))
")
    local slug
    slug=$(echo "$task_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')

    local result_dir="N/A"
    local coral_dir=""
    if [ -d "$CORAL_ROOT/results" ]; then
        for d in "$CORAL_ROOT/results/${slug}"*; do
            if [ -L "$d/latest" ]; then
                result_dir="$(readlink -f "$d/latest")"
                coral_dir="$d/latest/.coral"
                [ ! -d "$coral_dir" ] && coral_dir="$result_dir/.coral"
                break
            fi
        done
    fi

    local best_score="0"
    if [ -n "$coral_dir" ] && [ -d "$coral_dir" ]; then
        best_score=$(extract_best_score "$coral_dir")
    fi

    local status
    if [ "$best_score" != "0" ] && [ "$best_score" != "0.0000" ]; then
        status="completed"
    else
        status="no_score"
    fi
    echo "${problem_id},${problem_path},\"${cmd}\",${result_dir},${best_score},,,${status}" >> "$csv_file"
    echo "[DONE] $problem_id -> best_score=$best_score"
}

# Run a single problem with coral (blocks until timeout or early exit)
# Usage: run_one <problem_path> <runtime> <model>
run_one() {
    local problem_path="$1"
    local runtime="$2"
    local model="$3"
    local problem_id
    problem_id=$(basename "$problem_path")
    local task_yaml="$problem_path/task.yaml"

    # Build coral start command (1 agent, verbose, no internet)
    local cmd
    if [ "$runtime" = "codex" ]; then
        cmd="uv run coral start -c ${task_yaml} agents.count=1 agents.runtime=codex agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
    else
        cmd="uv run coral start -c ${task_yaml} agents.count=1 agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
    fi

    echo "[$(date '+%H:%M:%S')] START $problem_id | timeout ${TIMEOUT_SECONDS}s"

    cd "$CORAL_ROOT"
    timeout "${TIMEOUT_SECONDS}s" $cmd || true

    # If coral is still registered, stop it
    uv run coral stop --all 2>/dev/null || true
    echo "[$(date '+%H:%M:%S')] STOP  $problem_id"
}

# Run all problems in a group, 2 at a time
# Usage: run_group <csv_file> <runtime> <model> <problem1> <problem2> ...
run_group() {
    local csv_file="$1"
    local runtime="$2"
    local model="$3"
    shift 3
    local problems=("$@")
    local total=${#problems[@]}
    local i=0

    echo "Running $total problems, $PARALLEL at a time, ${TIMEOUT_SECONDS}s each"
    echo ""

    while [ $i -lt $total ]; do
        local pids=()
        local batch_problems=()

        # Launch up to PARALLEL problems
        for (( j=0; j<PARALLEL && i+j<total; j++ )); do
            local idx=$((i + j))
            local p="${problems[$idx]}"
            local pid_name=$(basename "$p")

            # Skip if already in CSV
            if grep -q "^${pid_name}," "$csv_file" 2>/dev/null; then
                echo "[SKIP] $pid_name already in CSV"
                continue
            fi

            local task_yaml="$p/task.yaml"
            if [ ! -f "$task_yaml" ]; then
                echo "[SKIP] $pid_name: task.yaml not found"
                echo "$(basename "$p"),${p},SKIP,,0,,,missing_task_yaml" >> "$csv_file"
                continue
            fi

            # Run in subshell so each problem has its own process group
            ( run_one "$p" "$runtime" "$model" ) &
            pids+=($!)
            batch_problems+=("$p")
        done

        # Wait for this batch to finish
        for pid in "${pids[@]}"; do
            wait "$pid" 2>/dev/null || true
        done

        # Collect results for this batch
        for p in "${batch_problems[@]}"; do
            local cmd_desc
            if [ "$runtime" = "codex" ]; then
                cmd_desc="uv run coral start -c ${p}/task.yaml agents.count=1 agents.runtime=codex agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
            else
                cmd_desc="uv run coral start -c ${p}/task.yaml agents.count=1 agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
            fi
            collect_result "$csv_file" "$p" "$cmd_desc"
        done

        i=$((i + PARALLEL))
    done
}

# Print summary of a CSV
print_summary() {
    local csv_file="$1"
    local group_name="$2"
    echo ""
    echo "================================================================"
    echo "  Summary for $group_name"
    echo "================================================================"
    echo ""
    column -t -s',' "$csv_file" 2>/dev/null || cat "$csv_file"
    echo ""
    local completed
    completed=$(tail -n +2 "$csv_file" | grep -c 'completed' || echo "0")
    local total
    total=$(tail -n +2 "$csv_file" | wc -l)
    echo "Completed with score: $completed / $total"
}
