# Diverse Conformer Portfolio

## 一句话解释

对每个分子，从很多候选构象里选出固定数量的构象，既要低能量，也要彼此差异大。

## 背景

同一个分子通常不只有一种三维形状，而是会有很多构象。

如果只选最低能量的几个构象，它们往往很像。
如果只追求多样性，又可能选到不稳定的构象。

所以这道题是在平衡两件事：

- 选中的构象要足够稳定
- 选中的构象之间要足够不同

## `baseline/init.py` 看到的输入

`prepare` 会产出一个纯算法 JSON：

```json
{
  "task_name": "diverse_conformer_portfolio_demo",
  "portfolio_size": 3,
  "energy_weight": 0.5,
  "diversity_weight": 3.0,
  "energy_cap_kcal_per_mol": 4.0,
  "rmsd_cap_angstrom": 2.5,
  "diversity_reward_exponent": 2.0,
  "molecules": [
    {
      "molecule_id": "mol_000",
      "conformers": [
        {
          "conformer_id": "mol_000_conf_000",
          "relative_energy_kcal_per_mol": 0.0
        }
      ],
      "pairwise_rmsd_angstrom": [
        [0.0, 1.2],
        [1.2, 0.0]
      ]
    }
  ]
}
```

可以把它当成一个“固定大小子集选择”问题：

- 每个点自己有节点奖励
- 每对点一起选还有配对奖励
- 必须恰好选 `portfolio_size` 个

## 输出格式

```json
{
  "selected_conformer_ids": {
    "mol_000": ["mol_000_conf_001", "mol_000_conf_004", "mol_000_conf_007"]
  }
}
```

要求：

- 每个分子都要给出答案
- 每个分子都必须恰好选 `portfolio_size` 个构象
- 不能重复

## 打分方式

若某个分子的选中集合是 `S`，总分为：

`score(S) = sum(node_reward(i) for i in S) + sum(pair_reward(i, j) for i < j, i,j in S)`

其中：

- `node_reward(i) = energy_weight * max(0, energy_cap - relative_energy_i)`
- `pair_reward(i, j) = diversity_weight * min(rmsd_ij, rmsd_cap) ^ diversity_reward_exponent`

总任务得分是所有分子得分之和。

## 这个可证上界是怎么得到的

这个任务不会在线精确求真最优，而是构造一个严格成立的上界。

对单个分子，评测脚本做三步：

1. 计算所有候选构象的节点奖励
   - 取最大的 `portfolio_size` 个
2. 计算所有候选构象对的配对奖励
   - 取最大的 `C(portfolio_size, 2)` 个
3. 把这两部分相加

得到的值一定不小于任何合法选择，因此它是 `certified_upper_bound`。

但要注意：

- 这不是精确最优
- 因为“最好的点”和“最好的边”不一定能来自同一个合法子集

## 当前 starter 水平

在 `2026-03-16` 的当前配置下：

- starter 分数
  - `278.215531`
- 可证上界
  - `674.897119`
- 相对差距
  - `58.777%`

## 为什么 starter 会差很多

当前 `baseline/init.py` 的策略是：

- 先找最低能量构象
- 再选一批离它最近的构象

这会让答案集中在一个局部区域里。

但当前评分里，多样性奖励被刻意放大，所以：

- 一堆彼此很像的构象
  - 会浪费名额
- 一组彼此差异更大的构象
  - 往往更容易拿高分

## 先从哪里优化

推荐从下面几步开始：

1. 用增量收益贪心代替“围着最低能量构象选”
2. 加 `1-swap` 局部搜索
3. 做多起点重启

进一步可以尝试：

- beam search
- tabu search
- 二次整数规划

## 化学库在做什么

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - 生成构象
  - 计算能量
  - 计算两两 RMSD
- `evaluate`
  - 对提交的构象子集打分
  - 计算可证上界

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
