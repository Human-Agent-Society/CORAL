# Predict Modality

This benchmark is adapted from OpenProblems Bio:

- Task repo: `openproblems-bio/task_predict_modality`
- Benchmark page: https://openproblems.bio/benchmarks/predict_modality

It evaluates predicting a target modality (here: **ADT / protein**) from an input modality (here: **RNA**), using the
public OpenProblems dataset hosted on `openproblems-data` (S3).

## Directory structure

- `baseline/`: simple reference methods (outputs `prediction.h5ad`)
- `verification/`: dataset downloader + scoring script
- `Task.md`: full task specification

## Quick start

Generate a baseline prediction (mean-per-protein):

```bash
python benchmarks/SingleCellAnalysis/predict_modality/baseline/run_mean_per_gene.py \
  --output prediction.h5ad
```

Evaluate a prediction:

```bash
python benchmarks/SingleCellAnalysis/predict_modality/verification/evaluate_predict_modality.py \
  --prediction prediction.h5ad
```

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=SingleCellAnalysis/predict_modality`

```bash
python -m frontier_eval task=unified task.benchmark=SingleCellAnalysis/predict_modality algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=predict_modality`.
