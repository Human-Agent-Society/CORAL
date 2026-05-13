# Predict Modality — Verification

This folder provides a lightweight scorer that reproduces the key OpenProblems predict-modality metrics on the public
dataset `openproblems_neurips2021/bmmc_cite/normal/log_cp10k` hosted on `openproblems-data` (S3).

## Setup

Create a venv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r benchmarks/SingleCellAnalysis/predict_modality/verification/requirements-predict_modality.txt
```

## Generate a baseline prediction

```bash
python benchmarks/SingleCellAnalysis/predict_modality/baseline/run_mean_per_gene.py \
  --output prediction.h5ad
```

## Score a prediction

```bash
python benchmarks/SingleCellAnalysis/predict_modality/verification/evaluate_predict_modality.py \
  --prediction prediction.h5ad
```

## Data download / cache

The scorer downloads the ground-truth `test_mod2.h5ad` into:

`benchmarks/SingleCellAnalysis/predict_modality/resources_cache/openproblems_neurips2021__bmmc_cite__normal__log_cp10k/`

If you run the baseline script, it will also download `test_mod1.h5ad` and `train_mod2.h5ad`.

