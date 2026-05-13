#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark dir}"
CANDIDATE_PATH="${3:-}"

HANDOUT_DIR="${BENCHMARK_DIR}/malloclab-handout"
MAKE_CLEAN_LOG="${BENCHMARK_DIR}/make_clean.log"
MAKE_LOG="${BENCHMARK_DIR}/make.log"
MDRIVER_STDOUT="${BENCHMARK_DIR}/mdriver.stdout.txt"
MDRIVER_STDERR="${BENCHMARK_DIR}/mdriver.stderr.txt"
METRICS_JSON="${BENCHMARK_DIR}/metrics.json"

cd "${HANDOUT_DIR}"

make clean >"${MAKE_CLEAN_LOG}" 2>&1
make >"${MAKE_LOG}" 2>&1

set +e
./mdriver -V >"${MDRIVER_STDOUT}" 2>"${MDRIVER_STDERR}"
MDRIVER_RC=$?
set -e

{
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "mdriver_returncode=${MDRIVER_RC}"
} > "${BENCHMARK_DIR}/run_meta.txt"

"${PYTHON_CMD}" "${BENCHMARK_DIR}/frontier_eval/parse_mdriver_result.py" \
  --stdout-file "${MDRIVER_STDOUT}" \
  --stderr-file "${MDRIVER_STDERR}" \
  --mdriver-returncode "${MDRIVER_RC}" \
  --metrics-out "${METRICS_JSON}"

# Always return 0 here: parsed `metrics.json` already encodes validity/score.
exit 0
