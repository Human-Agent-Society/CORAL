# 模态预测（OpenProblems / NeurIPS 2021 multiome）

## 1. 背景
多模态单细胞测序（如 CITE-seq 同时测量 RNA 与表面蛋白）能够更全面地刻画细胞状态，但实验成本仍然较高。
在已有一种模态的情况下预测另一种模态，有助于：

- 缺失模态补全（imputation）
- 不同技术/模态数据集的整合
- 需要统一表示的下游分析

本 benchmark 参考并改编自 OpenProblems Bio 的 `task_predict_modality` 仓库。

## 2. 数据集（来源）
使用 OpenProblems 在公共 `openproblems-data`（S3）上发布的处理后数据：

- dataset id：`openproblems_neurips2021/bmmc_cite/normal/log_cp10k`
- 文件：`train_mod1.h5ad`、`train_mod2.h5ad`、`test_mod1.h5ad`、`test_mod2.h5ad`

在该数据集中：

- mod1 = RNA（GEX）特征（normalized, log_cp10k）
- mod2 = ADT / 蛋白特征（normalized）

## 3. 任务定义
在训练集上学习 `(train_mod1 -> train_mod2)` 的映射，然后对测试细胞给定 `test_mod1` 预测其 `mod2`。

### 3.1 输出格式
写出 `prediction.h5ad`（AnnData）：

- `layers["normalized"]`：形状 `(n_test_cells, n_mod2_features)` 的预测矩阵
- `obs`：与 `test_mod1.obs` 一致（同一批细胞、同顺序）
- `var`：与 `train_mod2.var` 一致（同一组 mod2 特征、同顺序）
- `uns["dataset_id"]`：数据集标识
- `uns["method_id"]`：方法标识

## 4. 评测
评测对比 `test_mod2.layers["normalized"]`（真实）与 `prediction.layers["normalized"]`（预测）。

输出指标（与 OpenProblems 任务一致）：

- 误差：`rmse`、`mae`
- 相关性：
  - `mean_pearson_per_cell`、`mean_spearman_per_cell`
  - `mean_pearson_per_gene`、`mean_spearman_per_gene`
  - `overall_pearson`、`overall_spearman`

### 4.1 综合得分
将相关性与误差合成为单一可最大化得分：

- `corr_score = (mean_pearson_per_cell + 1) / 2`
- `err_score = 1 / (1 + rmse)`
- `combined_score = (corr_score + err_score) / 2`

得分越高越好；不合法输出得分为 0。

## 5. 参考
- OpenProblems 任务仓库：https://github.com/openproblems-bio/task_predict_modality
- OpenProblems Benchmark 页面：https://openproblems.bio/benchmarks/predict_modality

