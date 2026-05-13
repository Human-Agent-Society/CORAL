# Predict Modality（模态预测）

该任务基于 OpenProblems Bio 的真实公开数据与评测规范构建：

- Task 仓库：`openproblems-bio/task_predict_modality`
- Benchmark 页面：https://openproblems.bio/benchmarks/predict_modality

任务目标是在给定输入模态（本 benchmark 选择 **RNA**）的情况下，预测目标模态（本 benchmark 选择 **ADT/蛋白**）。
数据来自公开的 OpenProblems `openproblems-data`（S3）。

## 目录结构

- `baseline/`：简单 baseline（输出 `prediction.h5ad`）
- `verification/`：数据下载与打分脚本
- `Task.md`：任务说明与 I/O 规范

## 快速开始

生成 baseline 预测（按蛋白均值）：

```bash
python benchmarks/SingleCellAnalysis/predict_modality/baseline/run_mean_per_gene.py \
  --output prediction.h5ad
```

评测预测结果：

```bash
python benchmarks/SingleCellAnalysis/predict_modality/verification/evaluate_predict_modality.py \
  --prediction prediction.h5ad
```

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=SingleCellAnalysis/predict_modality`

```bash
python -m frontier_eval task=unified task.benchmark=SingleCellAnalysis/predict_modality algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=predict_modality`。
