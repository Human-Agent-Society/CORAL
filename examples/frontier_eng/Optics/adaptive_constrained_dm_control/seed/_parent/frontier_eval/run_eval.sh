#!/usr/bin/env bash
set -euo pipefail

INVALID_COMBINED_SCORE="-1e18"

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark dir}"
CANDIDATE_PATH="${3:-}"

if [[ "${BENCHMARK_DIR}" != /* ]]; then
  BENCHMARK_DIR="$(cd "${BENCHMARK_DIR}" && pwd -P)"
fi

if [[ -z "${CANDIDATE_PATH}" ]]; then
  CANDIDATE_PATH="${BENCHMARK_DIR}/baseline/init.py"
elif [[ "${CANDIDATE_PATH}" != /* ]]; then
  if [[ -f "${CANDIDATE_PATH}" ]]; then
    CANDIDATE_PATH="$(cd "$(dirname "${CANDIDATE_PATH}")" && pwd -P)/$(basename "${CANDIDATE_PATH}")"
  else
    CANDIDATE_PATH="${BENCHMARK_DIR}/${CANDIDATE_PATH}"
  fi
fi

TASK_NAME="$(basename "${BENCHMARK_DIR}")"
# In unified sandbox, benchmark dir is usually a fixed temp folder name `benchmark`.
# Recover real task name from source benchmark env var when available.
if [[ "${TASK_NAME}" == "benchmark" && -n "${FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR:-}" ]]; then
  TASK_NAME="$(basename "${FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR}")"
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

METRICS_JSON="${BENCHMARK_DIR}/metrics.json"
ARTIFACTS_JSON="${BENCHMARK_DIR}/artifacts.json"
EVAL_STDOUT="${BENCHMARK_DIR}/eval.stdout.txt"
EVAL_STDERR="${BENCHMARK_DIR}/eval.stderr.txt"
RUN_META="${BENCHMARK_DIR}/run_meta.txt"

TASK_KIND="unknown"
SOURCE_JSON_REL=""
declare -a EVAL_CMD

case "${TASK_NAME}" in
  adaptive_*)
    TASK_KIND="adaptive"
    SOURCE_JSON_REL="verification/outputs/metrics.json"
    EVAL_CMD=("${PYTHON_CMD}" "verification/evaluate.py" "--candidate" "${CANDIDATE_PATH}")
    ;;
  phase_*)
    TASK_KIND="phase"
    SOURCE_JSON_REL="verification/outputs/metrics.json"
    EVAL_CMD=("${PYTHON_CMD}" "verification/validate.py" "--output-dir" "verification/outputs")
    ;;
  fiber_*)
    TASK_KIND="fiber"
    SOURCE_JSON_REL="verification/outputs/summary.json"
    EVAL_CMD=("${PYTHON_CMD}" "verification/run_validation.py" "--solver" "${CANDIDATE_PATH}" "--out-dir" "verification/outputs")
    ;;
  holographic_*)
    TASK_KIND="holographic"
    SOURCE_JSON_REL="verification/artifacts/summary.json"
    EVAL_CMD=(
      "${PYTHON_CMD}" "verification/evaluate.py"
      "--device" "cpu"
      "--baseline-steps" "24"
      "--reference-steps" "40"
      "--artifacts-dir" "verification/artifacts"
    )
    ;;
  *)
    TASK_KIND="unknown"
    ;;
esac

rm -f "${METRICS_JSON}" "${ARTIFACTS_JSON}" "${EVAL_STDOUT}" "${EVAL_STDERR}" "${RUN_META}"
if [[ -n "${SOURCE_JSON_REL}" ]]; then
  rm -f "${BENCHMARK_DIR}/${SOURCE_JSON_REL}"
fi

START_TS="$(date +%s)"

if [[ "${TASK_KIND}" == "unknown" ]]; then
  EVAL_RC=2
  echo "Unsupported Optics task folder: ${TASK_NAME}" >"${EVAL_STDERR}"
else
  set +e
  (
    cd "${BENCHMARK_DIR}"
    "${EVAL_CMD[@]}"
  ) >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
  EVAL_RC=$?
  set -e
fi

END_TS="$(date +%s)"
ELAPSED_S=$((END_TS - START_TS))

SOURCE_JSON="${BENCHMARK_DIR}/${SOURCE_JSON_REL}"
set +e
"${PYTHON_CMD}" "${SCRIPT_DIR}/parse_result.py" \
  --task-kind "${TASK_KIND}" \
  --task-name "${TASK_NAME}" \
  --source-json "${SOURCE_JSON}" \
  --metrics-out "${METRICS_JSON}" \
  --artifacts-out "${ARTIFACTS_JSON}" \
  --eval-rc "${EVAL_RC}" \
  --runtime-s "${ELAPSED_S}" \
  --candidate "${CANDIDATE_PATH}" \
  --stdout-file "${EVAL_STDOUT}" \
  --stderr-file "${EVAL_STDERR}"
PARSE_RC=$?
set -e

if [[ ${PARSE_RC} -ne 0 || ! -f "${METRICS_JSON}" ]]; then
  cat > "${METRICS_JSON}" <<EOF
{
  "combined_score": ${INVALID_COMBINED_SCORE},
  "valid": 0.0,
  "eval_returncode": ${EVAL_RC},
  "runtime_s": ${ELAPSED_S}
}
EOF
fi

if [[ ! -f "${ARTIFACTS_JSON}" ]]; then
  cat > "${ARTIFACTS_JSON}" <<EOF
{
  "error_message": "failed to generate artifacts.json",
  "task_name": "${TASK_NAME}",
  "task_kind": "${TASK_KIND}",
  "eval_returncode": ${EVAL_RC}
}
EOF
fi

{
  echo "task_name=${TASK_NAME}"
  echo "task_kind=${TASK_KIND}"
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "eval_returncode=${EVAL_RC}"
  echo "parse_returncode=${PARSE_RC}"
  echo "runtime_s=${ELAPSED_S}"
  echo "source_json=${SOURCE_JSON}"
  echo "metrics_json=${METRICS_JSON}"
  echo "artifacts_json=${ARTIFACTS_JSON}"
} > "${RUN_META}"

# Keep return code 0 so unified reads validity/score from metrics.json.
exit 0
