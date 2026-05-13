#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="${1:?missing python command}"
BENCHMARK_DIR="${2:?missing benchmark dir}"
CANDIDATE_PATH="${3:-}"

if [[ "${BENCHMARK_DIR}" != /* ]]; then
  BENCHMARK_DIR="$(cd "${BENCHMARK_DIR}" && pwd -P)"
fi

if [[ -n "${CANDIDATE_PATH}" && "${CANDIDATE_PATH}" != /* ]]; then
  if [[ -f "${CANDIDATE_PATH}" ]]; then
    CANDIDATE_PATH="$(cd "$(dirname "${CANDIDATE_PATH}")" && pwd -P)/$(basename "${CANDIDATE_PATH}")"
  else
    CANDIDATE_PATH="${BENCHMARK_DIR}/${CANDIDATE_PATH}"
  fi
fi

MODE="${ENGDESIGN_EVAL_MODE:-auto}" # auto | docker | local
IMAGE_TAG="${ENGDESIGN_DOCKER_IMAGE:-engdesign-sim:frontier-eval}"
TASK_TIMEOUT_S="${ENGDESIGN_TASK_TIMEOUT_S:-180}"

METRICS_JSON="${BENCHMARK_DIR}/metrics.json"
ARTIFACTS_JSON="${BENCHMARK_DIR}/artifacts.json"
EVAL_STDOUT="${BENCHMARK_DIR}/eval.stdout.txt"
EVAL_STDERR="${BENCHMARK_DIR}/eval.stderr.txt"
RUN_META="${BENCHMARK_DIR}/run_meta.txt"
EVAL_SCRIPT="${BENCHMARK_DIR}/frontier_eval/evaluate_submission.py"

docker_ready() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

ensure_docker_image() {
  if docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
    return 0
  fi
  docker build -t "${IMAGE_TAG}" -f "${BENCHMARK_DIR}/Dockerfile" "${BENCHMARK_DIR}"
}

run_local() {
  "${PYTHON_CMD}" "${EVAL_SCRIPT}" \
    --candidate "${CANDIDATE_PATH}" \
    --benchmark-dir "${BENCHMARK_DIR}" \
    --metrics-out "${METRICS_JSON}" \
    --artifacts-out "${ARTIFACTS_JSON}" \
    --task-timeout-s "${TASK_TIMEOUT_S}"
}

run_docker() {
  if [[ "${CANDIDATE_PATH}" != "${BENCHMARK_DIR}/"* ]]; then
    echo "Candidate path must be under benchmark dir for docker mode: ${CANDIDATE_PATH}" >&2
    return 2
  fi

  local candidate_rel candidate_in_container inner_cmd
  candidate_rel="${CANDIDATE_PATH#${BENCHMARK_DIR}/}"
  candidate_in_container="/app/${candidate_rel}"

  ensure_docker_image
  inner_cmd="$(printf "python3 frontier_eval/evaluate_submission.py --candidate %q --benchmark-dir /app --metrics-out /app/metrics.json --artifacts-out /app/artifacts.json --task-timeout-s %q" "${candidate_in_container}" "${TASK_TIMEOUT_S}")"

  docker run --rm \
    -v "${BENCHMARK_DIR}:/app" \
    --workdir /app \
    --entrypoint bash \
    "${IMAGE_TAG}" \
    -lc "${inner_cmd}"
}

rm -f "${EVAL_STDOUT}" "${EVAL_STDERR}"

EVAL_MODE_USED=""
EVAL_RC=0
set +e
case "${MODE}" in
  docker)
    EVAL_MODE_USED="docker"
    run_docker >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
    EVAL_RC=$?
    ;;
  local)
    EVAL_MODE_USED="local"
    run_local >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
    EVAL_RC=$?
    ;;
  auto)
    if docker_ready; then
      EVAL_MODE_USED="docker"
      run_docker >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
      EVAL_RC=$?
      if [[ ${EVAL_RC} -ne 0 ]]; then
        echo "[run_eval] Docker run failed (rc=${EVAL_RC}), fallback to local mode." >>"${EVAL_STDERR}"
        EVAL_MODE_USED="local_fallback"
        run_local >>"${EVAL_STDOUT}" 2>>"${EVAL_STDERR}"
        EVAL_RC=$?
      fi
    else
      EVAL_MODE_USED="local"
      run_local >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
      EVAL_RC=$?
    fi
    ;;
  *)
    EVAL_MODE_USED="invalid_mode"
    echo "Unsupported ENGDESIGN_EVAL_MODE=${MODE}" >"${EVAL_STDERR}"
    EVAL_RC=2
    ;;
esac
set -e

{
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "eval_mode=${MODE}"
  echo "eval_mode_used=${EVAL_MODE_USED}"
  echo "eval_returncode=${EVAL_RC}"
  echo "docker_image=${IMAGE_TAG}"
  echo "task_timeout_s=${TASK_TIMEOUT_S}"
} > "${RUN_META}"

if [[ ! -f "${METRICS_JSON}" ]]; then
  cat > "${METRICS_JSON}" <<EOF
{
  "combined_score": 0.0,
  "valid": 0.0,
  "eval_returncode": ${EVAL_RC}
}
EOF
fi

if [[ ! -f "${ARTIFACTS_JSON}" ]]; then
  cat > "${ARTIFACTS_JSON}" <<EOF
{
  "error_message": "EngDesign evaluation failed before artifacts were produced.",
  "eval_mode_used": "${EVAL_MODE_USED}",
  "eval_returncode": ${EVAL_RC}
}
EOF
fi

# Keep return code 0. unified reads validity/score from metrics.json.
exit 0
