#!/bin/bash
# Common functions for competition runners
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORAL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMEOUT_SECONDS=$((90 * 60))  # 1.5 hours per problem
PARALLEL=1                     # run 1 problem at a time
EVAL_POLL_SECONDS=10           # refresh CSV when a higher score appears
GRADER_PYTHON_PATH="${GRADER_PYTHON_PATH:-$HOME/code/Frontier-CS/src}"  # python path for grader

# Initialize CSV for a group
# Usage: init_csv <group_name>
init_csv() {
    local group_name="$1"
    local csv="$RESULTS_DIR/${group_name}.csv"
    mkdir -p "$RESULTS_DIR"
    if [ ! -f "$csv" ]; then
        echo "problem_id,problem_path,command,result_dir,best_score,sota_score,gap_to_sota,status" > "$csv"
    fi
    echo "$csv"
}

# Upsert a CSV row for one problem. If the problem already exists, only replace
# the stored row when the new score is higher or when there is no previous row.
# Usage: upsert_csv_row <csv_file> <problem_id> <problem_path> <cmd> <result_dir> <best_score> <status>
upsert_csv_row() {
    local csv_file="$1"
    local problem_id="$2"
    local problem_path="$3"
    local cmd="$4"
    local result_dir="$5"
    local best_score="$6"
    local status="$7"

    python3 - "$csv_file" "$problem_id" "$problem_path" "$cmd" "$result_dir" "$best_score" "$status" <<'PY2'
import csv
import os
import sys

csv_file, problem_id, problem_path, cmd, result_dir, best_score, status = sys.argv[1:]
fieldnames = [
    "problem_id",
    "problem_path",
    "command",
    "result_dir",
    "best_score",
    "sota_score",
    "gap_to_sota",
    "status",
]

try:
    new_score = float(best_score)
except ValueError:
    new_score = 0.0

rows = []
existing = None
if os.path.exists(csv_file):
    with open(csv_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("problem_id") == problem_id:
                existing = row
            else:
                rows.append(row)

replace = existing is None
if existing is not None:
    try:
        old_score = float(existing.get("best_score", "0") or 0)
    except ValueError:
        old_score = 0.0
    replace = (
        new_score > old_score
        or existing.get("status", "") != status
        or existing.get("result_dir", "") != result_dir
        or existing.get("command", "") != cmd
        or existing.get("problem_path", "") != problem_path
    )

if replace:
    existing = {
        "problem_id": problem_id,
        "problem_path": problem_path,
        "command": cmd,
        "result_dir": result_dir,
        "best_score": best_score,
        "sota_score": existing.get("sota_score", "") if existing else "",
        "gap_to_sota": existing.get("gap_to_sota", "") if existing else "",
        "status": status,
    }

if existing is not None:
    rows.append(existing)

rows.sort(key=lambda row: row.get("problem_id", ""))

with open(csv_file, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
PY2
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

# Resolve the current result directory and .coral directory for a problem.
# Usage: get_result_context <problem_path>
get_result_context() {
    local problem_path="$1"
    local task_yaml="$problem_path/task.yaml"

    if [ ! -f "$task_yaml" ]; then
        echo "N/A|"
        return
    fi

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
            [ -e "$d" ] || continue
            if [ -L "$d/latest" ]; then
                result_dir="$(readlink -f "$d/latest")"
                coral_dir="$d/latest/.coral"
                [ ! -d "$coral_dir" ] && coral_dir="$result_dir/.coral"
                break
            fi
        done
    fi

    echo "${result_dir}|${coral_dir}"
}

# Collect result for a problem and upsert it into CSV
# Usage: collect_result <csv_file> <problem_path> <cmd>
collect_result() {
    local csv_file="$1"
    local problem_path="$2"
    local cmd="$3"
    local problem_id
    problem_id=$(basename "$problem_path")
    local context
    context=$(get_result_context "$problem_path")
    local result_dir="${context%%|*}"
    local coral_dir="${context#*|}"

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
    upsert_csv_row "$csv_file" "$problem_id" "$problem_path" "$cmd" "$result_dir" "$best_score" "$status"
    echo "[CSV] $problem_id -> best_score=$best_score status=$status"
}

# Monitor a running problem and refresh CSV whenever the score improves.
# Usage: watch_problem_progress <pid> <csv_file> <problem_path> <cmd>
watch_problem_progress() {
    local runner_pid="$1"
    local csv_file="$2"
    local problem_path="$3"
    local cmd="$4"
    local best_seen="-1"
    local problem_id
    problem_id=$(basename "$problem_path")

    while kill -0 "$runner_pid" 2>/dev/null; do
        local context
        context=$(get_result_context "$problem_path")
        local result_dir="${context%%|*}"
        local coral_dir="${context#*|}"

        if [ -n "$coral_dir" ] && [ -d "$coral_dir" ]; then
            local best_score
            best_score=$(extract_best_score "$coral_dir")
            local improved
            improved=$(python3 - "$best_score" "$best_seen" <<'PY2'
import sys
print('1' if float(sys.argv[1]) > float(sys.argv[2]) else '0')
PY2
)
            if [ "$improved" = "1" ]; then
                best_seen="$best_score"
                upsert_csv_row "$csv_file" "$problem_id" "$problem_path" "$cmd" "$result_dir" "$best_score" "running"
                echo "[EVAL] $problem_id -> improved to $best_score"
            fi
        fi

        sleep "$EVAL_POLL_SECONDS"
    done
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
    local python_path_override="grader.python_path=[${GRADER_PYTHON_PATH}]"
    if [ "$runtime" = "codex" ]; then
        cmd="uv run coral start -c ${task_yaml} agents.count=1 agents.runtime=codex agents.model=${model} run.verbose=true run.tmux=false agents.research=false ${python_path_override}"
    else
        cmd="uv run coral start -c ${task_yaml} agents.count=1 agents.model=${model} run.verbose=true run.tmux=false agents.research=false ${python_path_override}"
    fi

    echo "[$(date '+%H:%M:%S')] START $problem_id | timeout ${TIMEOUT_SECONDS}s"

    cd "$CORAL_ROOT"
    timeout "${TIMEOUT_SECONDS}s" $cmd || true

    # If coral is still registered, stop it
    uv run coral stop --all 2>/dev/null || true
    echo "[$(date '+%H:%M:%S')] STOP  $problem_id"
}

# Run all problems in a group, one at a time
# Usage: run_group <csv_file> <runtime> <model> <problem1> <problem2> ...
run_group() {
    local csv_file="$1"
    local runtime="$2"
    local model="$3"
    shift 3
    local problems=("$@")
    local total=${#problems[@]}
    local processed=0

    echo "Running $total problems, $PARALLEL at a time, ${TIMEOUT_SECONDS}s each"
    echo ""

    for p in "${problems[@]}"; do
        local pid_name
        pid_name=$(basename "$p")
        processed=$((processed + 1))

        local task_yaml="$p/task.yaml"
        if [ ! -f "$task_yaml" ]; then
            echo "[SKIP] $pid_name: task.yaml not found"
            upsert_csv_row "$csv_file" "$pid_name" "$p" "SKIP" "N/A" "0" "missing_task_yaml"
            continue
        fi

        local cmd_desc
        if [ "$runtime" = "codex" ]; then
            cmd_desc="uv run coral start -c ${p}/task.yaml agents.count=1 agents.runtime=codex agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
        else
            cmd_desc="uv run coral start -c ${p}/task.yaml agents.count=1 agents.model=${model} run.verbose=true run.tmux=false agents.research=false"
        fi

        echo "[QUEUE] ($processed/$total) $pid_name"

        ( run_one "$p" "$runtime" "$model" ) &
        local runner_pid=$!
        watch_problem_progress "$runner_pid" "$csv_file" "$p" "$cmd_desc"
        wait "$runner_pid" 2>/dev/null || true
        collect_result "$csv_file" "$p" "$cmd_desc"
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
