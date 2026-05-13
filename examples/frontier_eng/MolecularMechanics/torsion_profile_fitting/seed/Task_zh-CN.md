# Torsion Profile Fitting

## 一句话解释

调几个连续参数，让预测能量曲线尽量贴近目标曲线。

## 背景

分子绕一根键旋转时，不同角度通常对应不同能量。
把“角度 -> 相对能量”画出来，就是一条 torsion profile。

如果参数不合适，模型给出的曲线会和目标曲线不一致。

所以这道题的目标是：

- 调整若干缩放系数
- 让预测曲线尽量贴近目标曲线

## `baseline/init.py` 看到的输入

`prepare` 会生成一个纯算法 JSON：

```json
{
  "task_name": "torsion_profile_fitting_demo",
  "angles_degrees": [60, 120, 180, 240, 300],
  "tunable_terms": ["k1", "k2", "k3"],
  "term_scale_bounds": {
    "k1": [0.6, 1.8],
    "k2": [0.6, 1.8],
    "k3": [0.6, 1.8]
  },
  "score_penalty_per_rmse": 250.0,
  "target_relative_energies_kcal_per_mol": [4.6, 6.2, 0.0, 6.5, 8.6],
  "candidate_profiles": [
    {
      "candidate_id": "sample_0000",
      "term_scales": {"k1": 0.8, "k2": 1.2, "k3": 1.0},
      "relative_energies_kcal_per_mol": [4.1, 5.8, 0.0, 6.1, 8.1]
    }
  ]
}
```

这里最重要的一点是：

- `candidate_profiles`
  - 只是公开样本点
- 它不是完整搜索空间

## 输出格式

```json
{
  "term_scales": {
    "k1": 1.2,
    "k2": 1.6,
    "k3": 1.0
  }
}
```

要求：

- 每个参数都要给出
- 必须落在 `term_scale_bounds` 范围内

## 打分方式

先计算预测曲线与目标曲线的 RMSE：

`rmse = sqrt(mean((predicted_i - target_i)^2))`

再转为分数：

`score = max(0, 100 - score_penalty_per_rmse * rmse)`

所以：

- RMSE 越小越好
- score 越高越好

## 这些参考值是怎么得到的

这个任务会报告两个和优化水平有关的参考值：

- `public_sample_best_score`
- `known_optimal_score`

它们来源不同：

- `public_sample_best_score`
  - 评测时把 `candidate_profiles` 中每个公开样本都与目标曲线比较
  - 算出各自 RMSE 和 score
  - 取其中最高分
- `known_optimal_score`
  - 不是评测时在线优化得到的
  - 而是 benchmark 设计时写在 `data/raw_task.json` 里的已知最优值

当前这个 benchmark 中：

- `known_optimal_score = 100.0`

原因是分数公式本身最高就是 `100`，任务设计时把这作为理想最优值。

## 当前 starter 水平

在 `2026-03-16` 的当前配置下：

- starter 分数
  - `34.744169`
- 已知最优
  - `100.0`
- 相对差距
  - `65.256%`
- 公开样本最好分数
  - `81.876024`

## 为什么 starter 会差很多

当前 `baseline/init.py` 的策略非常弱：

- 直接把所有参数都固定在 `1.0`
- 完全没有利用 `candidate_profiles`

所以它甚至连“先从公开样本里挑一个最好的点”都没有做。

## 先从哪里优化

最划算的优化顺序通常是：

1. 先在公开样本里选最优点
2. 用公开样本拟合 surrogate
3. 在 surrogate 上做连续优化

## 化学库在做什么

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - 生成公开参数样本
  - 为每个样本计算整条能量曲线
- `evaluate`
  - 把你提交的连续参数真正写回力场
  - 重新计算曲线并打分

## 原始输入

[data/raw_task.json](data/raw_task.json)

## 运行方式

从当前任务目录运行：

```bash
mkdir -p outputs

python verification/evaluate.py prepare \
  --raw-task data/raw_task.json \
  --prepared-output outputs/prepared.json

python baseline/init.py \
  --prepared-input outputs/prepared.json \
  --solution-output outputs/solution.json

python verification/evaluate.py evaluate \
  --prepared-input outputs/prepared.json \
  --solution outputs/solution.json \
  --result-output outputs/result.json
```
