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

METRICS_JSON="${BENCHMARK_DIR}/metrics.json"
ARTIFACTS_JSON="${BENCHMARK_DIR}/artifacts.json"
REPORT_JSON="${BENCHMARK_DIR}/eval_report.json"
EVAL_STDOUT="${BENCHMARK_DIR}/eval.stdout.txt"
EVAL_STDERR="${BENCHMARK_DIR}/eval.stderr.txt"
RUN_META="${BENCHMARK_DIR}/run_meta.txt"
EVAL_ARTIFACT_DIR="${BENCHMARK_DIR}/runs/unified_eval"

rm -f "${METRICS_JSON}" "${ARTIFACTS_JSON}" "${REPORT_JSON}" "${EVAL_STDOUT}" "${EVAL_STDERR}"
rm -rf "${EVAL_ARTIFACT_DIR}"

START_TS="$(date +%s)"

set +e
"${PYTHON_CMD}" "${BENCHMARK_DIR}/verification/evaluate.py" \
  --json-out "${REPORT_JSON}" \
  --artifact-dir "${EVAL_ARTIFACT_DIR}" \
  >"${EVAL_STDOUT}" 2>"${EVAL_STDERR}"
EVAL_RC=$?
set -e

END_TS="$(date +%s)"
ELAPSED_S=$((END_TS - START_TS))

"${PYTHON_CMD}" - "${REPORT_JSON}" "${METRICS_JSON}" "${ARTIFACTS_JSON}" "${EVAL_RC}" "${ELAPSED_S}" "${CANDIDATE_PATH}" "${EVAL_ARTIFACT_DIR}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])
artifacts_path = Path(sys.argv[3])
eval_rc = int(sys.argv[4])
elapsed_s = float(sys.argv[5])
candidate_path = sys.argv[6]
eval_artifact_dir = sys.argv[7]
INVALID_COMBINED_SCORE = -1e18


def maybe_float(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None
    return None


metrics = {
    "combined_score": INVALID_COMBINED_SCORE,
    "valid": 0.0,
    "eval_returncode": float(eval_rc),
    "runtime_s": elapsed_s,
}
artifacts = {
    "candidate_path": candidate_path,
    "eval_report_path": str(report_path),
    "eval_artifact_dir": eval_artifact_dir,
    "eval_returncode": eval_rc,
}

report = None
if report_path.is_file():
    try:
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            report = loaded
        else:
            artifacts["error_message"] = "eval_report.json is not a JSON object"
    except Exception as exc:
        artifacts["error_message"] = f"failed to parse eval_report.json: {exc}"
else:
    artifacts["error_message"] = "missing eval_report.json"

summary = {}
results = []
if report is not None:
    task_name = report.get("task")
    if task_name is not None:
        artifacts["task_name"] = str(task_name)

    raw_summary = report.get("summary")
    if isinstance(raw_summary, dict):
        summary = raw_summary
        artifacts["summary"] = raw_summary
        for key, value in raw_summary.items():
            numeric = maybe_float(value)
            if numeric is not None:
                metrics[f"summary_{key}"] = numeric

    raw_results = report.get("results")
    if isinstance(raw_results, list):
        results = raw_results
        metrics["result_count"] = float(len(raw_results))
        artifacts["result_count"] = len(raw_results)

score_0_to_3 = maybe_float(summary.get("avg_candidate_score_0_to_3"))
if score_0_to_3 is None and results:
    values = []
    for row in results:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate")
        if not isinstance(candidate, dict):
            continue
        numeric = maybe_float(candidate.get("score_0_to_3"))
        if numeric is not None:
            values.append(numeric)
    if values:
        score_0_to_3 = sum(values) / float(len(values))

if score_0_to_3 is not None:
    metrics["candidate_score_0_to_3"] = float(score_0_to_3)
    metrics["candidate_score_ratio"] = float(score_0_to_3) / 3.0
    if eval_rc == 0 and report is not None:
        metrics["combined_score"] = float(score_0_to_3)
        metrics["valid"] = 1.0
elif eval_rc == 0 and report is not None:
    artifacts.setdefault("error_message", "missing candidate score in eval_report.json")

if eval_rc != 0:
    artifacts.setdefault("error_message", "verification/evaluate.py returned non-zero exit code")
    metrics["combined_score"] = INVALID_COMBINED_SCORE
    metrics["valid"] = 0.0
elif report is None or score_0_to_3 is None:
    artifacts.setdefault("error_message", "missing candidate score in eval_report.json")
    metrics["combined_score"] = INVALID_COMBINED_SCORE
    metrics["valid"] = 0.0

metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")
artifacts_path.write_text(json.dumps(artifacts, indent=2, ensure_ascii=False), encoding="utf-8")
PY

{
  echo "candidate_path=${CANDIDATE_PATH}"
  echo "eval_returncode=${EVAL_RC}"
  echo "runtime_s=${ELAPSED_S}"
  echo "report_json=${REPORT_JSON}"
  echo "metrics_json=${METRICS_JSON}"
  echo "artifacts_json=${ARTIFACTS_JSON}"
  echo "artifact_dir=${EVAL_ARTIFACT_DIR}"
} > "${RUN_META}"

exit 0
