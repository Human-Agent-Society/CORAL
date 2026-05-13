# 拓扑优化

## 1. 问题

在固定材料预算下优化二维 MBB 梁的密度场。
目标是在体积分数约束下最小化柔顺度，从而得到轻量且刚度高的结构。

## 2. 设计变量

设：

- `nelx = 60`
- `nely = 20`

解是一个密度场，包含：

```text
60 * 20 = 1200
```

个单元密度值。

提交时将其存储为展平数组：

```text
density_vector
```

评测器会将其重塑为 `(nely, nelx)` 的密度场。

## 3. 物理模型

评测器使用：

- 二维四边形有限元（Q4）
- 平面应力本构模型
- SIMP 材料插值
- MBB 半梁边界条件

材料与优化参数来自 `references/problem_config.json`：

- `volfrac = 0.5`
- `penal = 3.0`
- `rmin = 1.5`
- `E0 = 1.0`
- `Emin = 1e-9`
- `nu = 0.3`

在左上节点施加向下的力。

## 4. 目标

最小化结构柔顺度：

```text
c = F^T u
```

柔顺度越低，结构越刚，分数越好。

## 5. 约束

平均密度必须满足：

```text
mean(density) <= volfrac
```

评测前，评测器会将每个密度裁剪到 `[1e-3, 1.0]`。

## 6. 提交格式

你的程序必须写出 `temp/submission.json`，结构如下：

```json
{
  "benchmark_id": "topology_optimization",
  "density_vector": [0.5, 0.5, 0.5],
  "nelx": 60,
  "nely": 20
}
```

要求：

- `density_vector` 长度必须等于 `nelx * nely = 1200`
- 所有条目必须是有限数值
- 输出格式必须保持不变

## 7. 可行性规则

出现以下任一情况则提交不可行：

1. 缺少 `submission.json`
2. 缺少 `density_vector`
3. 向量长度错误
4. 向量包含 `NaN` 或 `Inf`
5. FEM 求解失败
6. 平均密度超过体积分数限制

## 8. 评测流程

验证脚本会：

1. 在临时工作目录中运行候选程序
2. 加载 `temp/submission.json`
3. 校验密度向量
4. 独立求解 FEM 系统
5. 计算柔顺度和体积分数
6. 返回可行性与分数

运行：

```bash
python verification/evaluator.py scripts/init.py
```

## 9. 评分

- **可行**: 分数 = 柔顺度，越低越好
- **不可行**: 无效结果
- 在 `frontier_eval` 中，可行解使用 `combined_score = -compliance`

## 10. 参考

- 问题配置：`references/problem_config.json`
- 基线求解器：`scripts/init.py`
- 评测器：`verification/evaluator.py`
