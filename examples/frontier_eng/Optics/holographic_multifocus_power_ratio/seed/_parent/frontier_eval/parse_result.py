#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
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


def _get(mapping: dict[str, Any], *path: str) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _extract_adaptive(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    artifacts: dict[str, Any] = {}

    # Adaptive validators do not expose an explicit `valid` field; successful
    # payload generation implies a valid run.
    metrics["valid"] = 1.0

    cand_score = _maybe_float(_get(payload, "baseline", "score_0_to_1_higher_is_better"))
    cand_score_pct = _maybe_float(_get(payload, "baseline", "score_percent"))
    if cand_score is None and cand_score_pct is not None:
        cand_score = cand_score_pct / 100.0 if cand_score_pct > 1.0 else cand_score_pct
    if cand_score_pct is None and cand_score is not None:
        cand_score_pct = cand_score * 100.0

    ref_score = _maybe_float(_get(payload, "reference", "score_0_to_1_higher_is_better"))
    ref_score_pct = _maybe_float(_get(payload, "reference", "score_percent"))

    if cand_score is not None:
        metrics["candidate_score"] = float(cand_score)
        metrics["combined_score"] = float(cand_score)
    if cand_score_pct is not None:
        metrics["candidate_score_pct"] = float(cand_score_pct)

    if ref_score is not None:
        metrics["oracle_score"] = float(ref_score)
    if ref_score_pct is not None:
        metrics["oracle_score_pct"] = float(ref_score_pct)
    if cand_score is not None and ref_score is not None:
        metrics["score_gap_oracle_minus_candidate"] = float(ref_score - cand_score)

    for k in ("mean_rms", "mean_strehl", "mean_slew", "mean_abs_command", "p95_rms"):
        v = _maybe_float(_get(payload, "baseline", k))
        if v is not None:
            metrics[f"candidate_{k}"] = float(v)

    return metrics, artifacts


def _extract_phase(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    artifacts: dict[str, Any] = {}

    cand_score_raw = _maybe_float(_get(payload, "baseline", "score"))
    cand_score_pct = _maybe_float(_get(payload, "baseline", "score_pct"))
    if cand_score_pct is None:
        cand_score_pct = _maybe_float(_get(payload, "baseline", "score_percent"))
    cand_score = cand_score_raw
    if cand_score is None and cand_score_pct is not None:
        cand_score = float(cand_score_pct / 100.0 if cand_score_pct > 1.0 else cand_score_pct)
    elif cand_score is not None and cand_score > 1.0:
        cand_score = float(cand_score / 100.0)

    if cand_score is not None:
        metrics["candidate_score"] = float(cand_score)

    if cand_score_pct is None and cand_score is not None:
        cand_score_pct = float(cand_score * 100.0)
    if cand_score_pct is not None:
        metrics["candidate_score_pct"] = float(cand_score_pct)

    # For tasks that expose explicit `score`, keep 0-1 as optimization scale.
    # Otherwise preserve legacy phase task behavior (native score_pct in 0-100).
    if cand_score_raw is not None and cand_score is not None:
        metrics["combined_score"] = float(cand_score)
    elif cand_score_pct is not None:
        metrics["combined_score"] = float(cand_score_pct)

    ref_score_raw = _maybe_float(_get(payload, "oracle", "score"))
    ref_score_pct = _maybe_float(_get(payload, "oracle", "score_pct"))
    if ref_score_pct is None:
        ref_score_pct = _maybe_float(_get(payload, "oracle", "score_percent"))
    ref_score = ref_score_raw
    if ref_score is None and ref_score_pct is not None:
        ref_score = float(ref_score_pct / 100.0 if ref_score_pct > 1.0 else ref_score_pct)
    elif ref_score is not None and ref_score > 1.0:
        ref_score = float(ref_score / 100.0)

    if ref_score is not None:
        metrics["oracle_score"] = float(ref_score)
    if ref_score_pct is None and ref_score is not None:
        ref_score_pct = float(ref_score * 100.0)
    if ref_score_pct is not None:
        metrics["oracle_score_pct"] = float(ref_score_pct)

    if cand_score is not None and ref_score is not None:
        metrics["score_gap_oracle_minus_candidate"] = float(ref_score - cand_score)

    valid_hint = _maybe_float(payload.get("valid"))
    if valid_hint is not None:
        metrics["valid"] = float(valid_hint)

    for k in ("ratio_mae", "cv_spots", "efficiency", "min_peak_ratio", "nmse", "energy_in_target", "dark_suppression"):
        v = _maybe_float(_get(payload, "baseline", k))
        if v is not None:
            metrics[f"candidate_{k}"] = float(v)

    return metrics, artifacts


def _extract_fiber(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    artifacts: dict[str, Any] = {}

    cand_score = _maybe_float(_get(payload, "candidate", "score"))
    if cand_score is not None:
        metrics["candidate_score"] = float(cand_score)
        metrics["combined_score"] = float(cand_score)

    cand_valid = _maybe_float(_get(payload, "candidate", "is_valid"))
    if cand_valid is None:
        cand_valid = _maybe_float(payload.get("is_valid"))
    if cand_valid is not None:
        metrics["valid"] = float(cand_valid)

    ref_score = _maybe_float(_get(payload, "oracle", "score"))
    if ref_score is not None:
        metrics["oracle_score"] = float(ref_score)

    gap = _maybe_float(payload.get("score_gap_oracle_minus_candidate"))
    if gap is not None:
        metrics["score_gap_oracle_minus_candidate"] = float(gap)

    for k in ("demand_satisfaction", "ber_pass_ratio", "spectral_utilization", "avg_snr_db", "latency_s", "acceptance_ratio"):
        v = _maybe_float(_get(payload, "candidate", k))
        if v is not None:
            metrics[f"candidate_{k}"] = float(v)

    return metrics, artifacts


def _extract_holographic_score(section: Any) -> tuple[float | None, float | None]:
    if not isinstance(section, dict):
        return None, None

    metrics_blob = section.get("metrics")
    if isinstance(metrics_blob, dict):
        score = _maybe_float(metrics_blob.get("score"))
        score_pct = _maybe_float(metrics_blob.get("score_pct"))
        if score is not None:
            if score_pct is None and 0.0 <= score <= 1.0:
                score_pct = score * 100.0
            return float(score), (float(score_pct) if score_pct is not None else None)
        if score_pct is not None:
            return float(score_pct / 100.0), float(score_pct)

    score = _maybe_float(section.get("mean_score"))
    if score is not None:
        return float(score), float(score * 100.0)

    score = _maybe_float(section.get("score"))
    if score is not None:
        score_pct = score * 100.0 if 0.0 <= score <= 1.0 else None
        return float(score), (float(score_pct) if score_pct is not None else None)

    score_pct = _maybe_float(section.get("score_pct"))
    if score_pct is not None:
        return float(score_pct / 100.0), float(score_pct)

    return None, None


def _extract_holographic(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    artifacts: dict[str, Any] = {}

    cand_score, cand_score_pct = _extract_holographic_score(payload.get("baseline"))
    if cand_score is not None:
        metrics["candidate_score"] = float(cand_score)
        metrics["combined_score"] = float(cand_score)
    if cand_score_pct is not None:
        metrics["candidate_score_pct"] = float(cand_score_pct)

    ref_score, ref_score_pct = _extract_holographic_score(payload.get("reference"))
    if ref_score is not None:
        metrics["oracle_score"] = float(ref_score)
    if ref_score_pct is not None:
        metrics["oracle_score_pct"] = float(ref_score_pct)
    if cand_score is not None and ref_score is not None:
        metrics["score_gap_oracle_minus_candidate"] = float(ref_score - cand_score)

    valid_hint = _maybe_float(_get(payload, "baseline", "valid"))
    if valid_hint is not None:
        metrics["valid"] = float(valid_hint)

    for k in ("mean_ratio_mae", "mean_efficiency", "mean_match", "separation", "mean_target_efficiency", "mean_crosstalk"):
        v = _maybe_float(_get(payload, "baseline", k))
        if v is not None:
            metrics[f"candidate_{k}"] = float(v)

    better = _maybe_float(_get(payload, "reference", "better_than_baseline"))
    if better is not None:
        metrics["reference_better_than_baseline"] = float(better)

    return metrics, artifacts


def _extract_by_kind(task_kind: str, payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    if task_kind == "adaptive":
        return _extract_adaptive(payload)
    if task_kind == "phase":
        return _extract_phase(payload)
    if task_kind == "fiber":
        return _extract_fiber(payload)
    if task_kind == "holographic":
        return _extract_holographic(payload)
    return {}, {"error_message": f"unsupported task kind: {task_kind}"}


def _finalize_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    finalized: dict[str, float] = {}
    for key, value in metrics.items():
        numeric = _maybe_float(value)
        if numeric is None:
            continue
        finalized[str(key)] = float(numeric)
    return finalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Optics evaluator outputs into unified metrics/artifacts.")
    parser.add_argument("--task-kind", required=True, choices=["adaptive", "phase", "fiber", "holographic", "unknown"])
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--source-json", type=Path, required=True)
    parser.add_argument("--metrics-out", type=Path, required=True)
    parser.add_argument("--artifacts-out", type=Path, required=True)
    parser.add_argument("--eval-rc", type=int, required=True)
    parser.add_argument("--runtime-s", type=float, required=True)
    parser.add_argument("--candidate", default="")
    parser.add_argument("--stdout-file", default="")
    parser.add_argument("--stderr-file", default="")
    args = parser.parse_args()

    metrics: dict[str, Any] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
        "eval_returncode": float(args.eval_rc),
        "runtime_s": float(args.runtime_s),
    }
    artifacts: dict[str, Any] = {
        "task_name": args.task_name,
        "task_kind": args.task_kind,
        "candidate_path": args.candidate,
        "source_json_path": str(args.source_json),
        "stdout_file": args.stdout_file,
        "stderr_file": args.stderr_file,
        "eval_returncode": args.eval_rc,
        "runtime_s": float(args.runtime_s),
    }

    payload: dict[str, Any] | None = None
    if args.source_json.is_file():
        try:
            loaded = json.loads(args.source_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
                artifacts["source_json_exists"] = True
                artifacts["source_json_keys"] = sorted(str(k) for k in loaded.keys())
            else:
                artifacts["source_json_exists"] = True
                artifacts["error_message"] = "source JSON is not an object"
        except Exception as exc:
            artifacts["source_json_exists"] = True
            artifacts["error_message"] = f"failed to parse source JSON: {exc}"
    else:
        artifacts["source_json_exists"] = False
        artifacts["error_message"] = "source JSON file missing"

    if payload is not None and args.task_kind != "unknown":
        parsed_metrics, parsed_artifacts = _extract_by_kind(args.task_kind, payload)
        metrics.update(parsed_metrics)
        artifacts.update(parsed_artifacts)

    # Fallback validity if parser did not set it explicitly.
    if "valid" not in metrics:
        metrics["valid"] = 1.0 if (args.eval_rc == 0 and payload is not None) else 0.0

    # Keep invalid runs strictly below any feasible score, including negative ones.
    valid_v = _maybe_float(metrics.get("valid")) or 0.0
    if args.eval_rc != 0 or valid_v <= 0.0:
        metrics["valid"] = 0.0
        metrics["combined_score"] = INVALID_COMBINED_SCORE
    elif "combined_score" not in metrics:
        cand = _maybe_float(metrics.get("candidate_score"))
        metrics["combined_score"] = float(cand) if cand is not None else 1.0

    clean_metrics = _finalize_metrics(metrics)

    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.artifacts_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(clean_metrics, indent=2, ensure_ascii=True), encoding="utf-8")
    args.artifacts_out.write_text(json.dumps(artifacts, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
