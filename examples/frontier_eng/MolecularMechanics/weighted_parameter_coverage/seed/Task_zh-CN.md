# Weighted Parameter Coverage

## 一句话解释

从很多候选项里，在预算限制下选出一小部分，让覆盖到的高价值特征尽量多。

## 背景

在真实 OpenFF 工作流里，一个分子会命中一组力场参数。

如果你想构造一个好的测试集，目标通常不是“挑很多分子”，而是：

- 用尽量少的分子
- 覆盖尽量多的参数
- 尤其覆盖稀有参数

在这个 benchmark 里，化学部分已经被转换成一个纯组合优化问题，所以你不需要懂力场细节。

## `baseline/init.py` 看到的输入

`prepare` 会生成一个纯算法 JSON：

```json
{
  "task_name": "rare_parameter_coverage_demo",
  "budget": 4,
  "feature_weights": {
    "feat_1": 1.0,
    "feat_2": 0.5
  },
  "candidates": [
    {
      "candidate_id": "mol_000",
      "name": "aspirin",
      "covered_features": ["feat_1", "feat_2"]
    }
  ]
}
```

你可以把它理解成：

- `budget`
  - 最多能选多少个候选项
- `feature_weights`
  - 每个特征的价值
- `covered_features`
  - 这个候选项能覆盖哪些特征

## 输出格式

`baseline/init.py` 需要输出：

```json
{
  "selected_candidate_ids": ["mol_001", "mol_007"]
}
```

要求：

- 不能超过 `budget`
- 不能重复选择同一个候选项

## 打分方式

把所有已选候选项覆盖到的特征取并集，记为 `U`。

总分为：

`score = sum(feature_weights[f] for f in U)`

分数越高越好。

## 这些参考值是怎么得到的

这个任务会显式给出：

- `exact_optimal_score`
- `certified_upper_bound`

这里两者相同，因为评测脚本会把问题精确改写成一个整数规划并求解：

- `x_i`
  - 是否选择第 `i` 个候选项
- `y_f`
  - 特征 `f` 是否被覆盖

优化目标：

- 最大化 `sum(feature_weights[f] * y_f)`

约束：

- `sum(x_i) <= budget`
- 如果没有任何已选候选项覆盖特征 `f`，就不能让 `y_f = 1`

因此：

- `exact_optimal_score`
  - 是当前实例的真最优
- `certified_upper_bound`
  - 在这里直接等于真最优

## 当前 starter 水平

在 `2026-03-16` 的当前配置下：

- starter 分数
  - `9.077764`
- 真最优
  - `24.579023`
- 相对差距
  - `63.067%`

## 为什么 starter 会差很多

当前 `baseline/init.py` 很弱：

- 它只看每个候选项单独覆盖了多少特征
- 它不关心候选项之间是否高度重叠
- 它也不专门偏向那些更稀有、更值钱的特征

所以它抓住了“看起来大”的集合，却经常错过“组合起来更互补”的集合。

## 先从哪里优化

最值得先做的几步是：

1. 用边际增益贪心替代静态排序
2. 在贪心解上做 `1-swap` 或 `2-swap`
3. 做多次随机重启

## 化学库在做什么

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - 用 OpenFF Toolkit 把分子转成特征集合
- `evaluate`
  - 按覆盖规则打分
  - 用整数规划精确求最优值

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
