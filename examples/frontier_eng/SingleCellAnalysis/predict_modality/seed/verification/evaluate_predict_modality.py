from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import anndata as ad
import numpy as np
from scipy import sparse
from scipy.stats import rankdata


DATASET_ID = "openproblems_neurips2021/bmmc_cite/normal/log_cp10k"
BASE_URL = (
    "https://openproblems-data.s3.amazonaws.com/"
    "resources/task_predict_modality/datasets/openproblems_neurips2021/bmmc_cite/normal/log_cp10k/"
)


def _repo_root(start: Path) -> Path:
    here = start.resolve()
    for parent in [here, *here.parents]:
        if (parent / "benchmarks").is_dir():
            return parent
    return here


def _download(url: str, dest: Path, *, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for _ in range(max(1, retries)):
        tmp = dest.parent / f".{dest.name}.tmp.{os.getpid()}.{time.time_ns()}"
        try:
            with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(dest)
            return
        except Exception as e:  # pragma: no cover
            last_err = e
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(1.0)
    raise RuntimeError(f"Failed to download {url} -> {dest}: {last_err}")


def _ensure_truth(dataset_dir: Path) -> Path:
    truth = dataset_dir / "test_mod2.h5ad"
    if not truth.is_file():
        _download(BASE_URL + "test_mod2.h5ad", truth)
    return truth


def _as_dense(x) -> np.ndarray:
    if sparse.issparse(x):
        return x.toarray()
    return np.asarray(x)


def _pearson_1d(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    x = np.nan_to_num(x, copy=False)
    y = np.nan_to_num(y, copy=False)
    xc = x - x.mean()
    yc = y - y.mean()
    den = float(np.linalg.norm(xc) * np.linalg.norm(yc))
    if den <= 0:
        return 0.0
    v = float(np.dot(xc, yc) / den)
    if not math.isfinite(v):
        return 0.0
    return v


def _spearman_1d(x: np.ndarray, y: np.ndarray) -> float:
    rx = rankdata(np.nan_to_num(np.asarray(x, dtype=np.float64)), method="average")
    ry = rankdata(np.nan_to_num(np.asarray(y, dtype=np.float64)), method="average")
    return _pearson_1d(rx, ry)


def evaluate(prediction_path: str, *, dataset_dir: Path) -> Any:
    start = time.time()
    truth_path = _ensure_truth(dataset_dir)

    sol = ad.read_h5ad(str(truth_path))
    pred = ad.read_h5ad(prediction_path)

    if sol.uns.get("dataset_id") != pred.uns.get("dataset_id"):
        raise ValueError("Prediction and solution have differing dataset_ids")
    if sol.shape != pred.shape:
        raise ValueError(f"Shape mismatch: solution {sol.shape} vs prediction {pred.shape}")
    if "normalized" not in sol.layers or "normalized" not in pred.layers:
        raise ValueError("Both solution and prediction must contain layers['normalized']")

    sol_obs = sol.obs_names.astype(str).tolist()
    pred_obs = pred.obs_names.astype(str).tolist()
    if sol_obs != pred_obs:
        if set(sol_obs) != set(pred_obs):
            raise ValueError("Prediction obs_names must match test_mod2 obs_names.")
        pred = pred[sol_obs]

    sol_var = sol.var_names.astype(str).tolist()
    pred_var = pred.var_names.astype(str).tolist()
    if sol_var != pred_var:
        if set(sol_var) != set(pred_var):
            raise ValueError("Prediction var_names must match test_mod2 var_names.")
        pred = pred[:, sol_var]

    tv = _as_dense(sol.layers["normalized"]).astype(np.float64, copy=False)
    pv = _as_dense(pred.layers["normalized"]).astype(np.float64, copy=False)
    pv = np.nan_to_num(pv, copy=False)

    diff = tv - pv
    rmse = float(np.sqrt(np.mean(diff * diff)))
    mae = float(np.mean(np.abs(diff)))

    # Per-cell correlations (row-wise).
    pearson_cell = np.array([_pearson_1d(tv[i], pv[i]) for i in range(tv.shape[0])], dtype=np.float64)
    spearman_cell = np.array([_spearman_1d(tv[i], pv[i]) for i in range(tv.shape[0])], dtype=np.float64)
    mean_pearson_per_cell = float(np.mean(pearson_cell))
    mean_spearman_per_cell = float(np.mean(spearman_cell))

    # Per-feature correlations (column-wise).
    pearson_gene = np.array([_pearson_1d(tv[:, j], pv[:, j]) for j in range(tv.shape[1])], dtype=np.float64)
    spearman_gene = np.array([_spearman_1d(tv[:, j], pv[:, j]) for j in range(tv.shape[1])], dtype=np.float64)
    mean_pearson_per_gene = float(np.mean(pearson_gene))
    mean_spearman_per_gene = float(np.mean(spearman_gene))

    overall_pearson = _pearson_1d(tv.ravel(), pv.ravel())
    overall_spearman = _spearman_1d(tv.ravel(), pv.ravel())

    corr_score = (mean_pearson_per_cell + 1.0) / 2.0
    err_score = 1.0 / (1.0 + rmse)
    combined = float((corr_score + err_score) / 2.0)

    metrics = {
        "combined_score": combined,
        "rmse": rmse,
        "mae": mae,
        "mean_pearson_per_cell": mean_pearson_per_cell,
        "mean_spearman_per_cell": mean_spearman_per_cell,
        "mean_pearson_per_gene": mean_pearson_per_gene,
        "mean_spearman_per_gene": mean_spearman_per_gene,
        "overall_pearson": float(overall_pearson),
        "overall_spearman": float(overall_spearman),
        "n_cells": float(tv.shape[0]),
        "n_features": float(tv.shape[1]),
        "runtime_s": float(time.time() - start),
        "dataset_id": str(sol.uns.get("dataset_id", DATASET_ID)),
        "method_id": str(pred.uns.get("method_id", "")),
        "valid": 1.0,
    }

    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts={})


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prediction", type=Path, required=True, help="Path to prediction.h5ad")
    p.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Cache directory for downloaded OpenProblems files (default: <benchmark>/resources_cache).",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root(Path(__file__).resolve())
    if args.dataset_dir is None:
        args.dataset_dir = (
            repo_root
            / "benchmarks"
            / "SingleCellAnalysis"
            / "predict_modality"
            / "resources_cache"
            / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
        )
    result = evaluate(str(args.prediction), dataset_dir=args.dataset_dir)
    try:
        metrics = result.metrics  # type: ignore[attr-defined]
    except Exception:
        metrics = result
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
