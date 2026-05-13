# Predict Modality (OpenProblems / NeurIPS 2021 multiome)

## 1. Background
Multi-modal single-cell assays (e.g., CITE-seq measuring RNA + surface proteins) enable deeper characterization of cell
state, but are still expensive. Predicting one modality from another is useful for:

- imputation of missing modalities
- integration of datasets measured with different technologies
- downstream analyses requiring a common representation

This benchmark is adapted from the OpenProblems Bio predict modality task repository:
`openproblems-bio/task_predict_modality`.

## 2. Dataset (source)
We use the OpenProblems processed dataset published to the public `openproblems-data` S3 bucket:

- dataset id: `openproblems_neurips2021/bmmc_cite/normal/log_cp10k`
- files: `train_mod1.h5ad`, `train_mod2.h5ad`, `test_mod1.h5ad`, `test_mod2.h5ad`

In this dataset:

- mod1 = RNA (GEX) features (normalized, log_cp10k)
- mod2 = ADT / protein features (normalized)

## 3. Task definition
Train a model on `(train_mod1 -> train_mod2)`, then predict `mod2` for the test cells given `test_mod1`.

### 3.1 Output format
Write a prediction file `prediction.h5ad` as an AnnData object:

- `layers["normalized"]`: a matrix of shape `(n_test_cells, n_mod2_features)` with predicted mod2 values
- `obs`: must match `test_mod1.obs` (same cells/order)
- `var`: must match `train_mod2.var` (same mod2 features/order)
- `uns["dataset_id"]`: string (copied from the dataset)
- `uns["method_id"]`: string (your method name)

## 4. Evaluation
The evaluator compares `test_mod2.layers["normalized"]` (truth) with `prediction.layers["normalized"]` (prediction).

Reported metrics (matching the OpenProblems task metrics):

- error: `rmse`, `mae`
- correlation:
  - `mean_pearson_per_cell`, `mean_spearman_per_cell`
  - `mean_pearson_per_gene`, `mean_spearman_per_gene`
  - `overall_pearson`, `overall_spearman`

### 4.1 Combined score
We convert correlation and error into a single maximization score:

- `corr_score = (mean_pearson_per_cell + 1) / 2`
- `err_score = 1 / (1 + rmse)`
- `combined_score = (corr_score + err_score) / 2`

Higher is better. Invalid submissions receive score 0.

## 5. References
- OpenProblems Bio task repo: https://github.com/openproblems-bio/task_predict_modality
- OpenProblems benchmarks: https://openproblems.bio/benchmarks/predict_modality

