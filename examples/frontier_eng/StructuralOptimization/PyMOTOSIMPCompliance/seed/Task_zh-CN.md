# PyMOTO SIMP 柔度优化任务说明

## 1. 问题定义

在固定材料预算（体积分数约束）下，为二维承载结构设计材料密度分布。
目标是在满足约束的前提下最小化结构柔度（compliance）。

## 2. 工程背景

该问题对应结构与机械设计中的经典轻量化场景：

- 支架、悬臂梁、桥式构件减重设计
- 在给定载荷下提升结构刚度
- 在性能与材料成本之间做工程权衡

任务实现采用受 pyMOTO 启发的密度法拓扑优化范式。

## 3. 设计变量

设：

- `nelx = 50`
- `nely = 16`

提交变量为展平密度向量：

```text
density_vector in R^(nelx * nely) = R^800
```

评测器会将密度裁剪到：

```text
[rho_min, 1.0], rho_min = 1e-9
```

## 4. 物理模型与边界条件

评测器使用独立有限元流程：

1. 构建二维网格域
2. 左边界全自由度固定
3. 右侧中点施加 y 向集中载荷
4. 使用 SIMP 插值：

```text
E(x) = Emin + (E0 - Emin) * x^penal
```

5. 组装刚度矩阵并求解位移
6. 计算柔度：

```text
c = F^T u
```

具体参数见 `references/problem_config.json`。

## 5. 目标与约束

### 目标

最小化柔度 `c`。

### 约束

材料体积分数约束：

```text
mean(density) <= volfrac
```

评测器内部带可行性容差。

## 6. 候选程序契约

候选文件：`scripts/init.py`

候选程序必须输出 `temp/submission.json`，至少包含：

- `density_vector`

评测器不会信任候选自报得分，会独立重算。

## 7. Agent 可优化内容

在 `scripts/init.py` 内，Agent 可优化策略层逻辑，例如：

- 密度更新规则
- 允许范围内的滤波策略
- 步长或迭代调度
- OC 更新策略与调度

评测器与 benchmark 元数据文件为只读。

## 8. 评测流程

给定候选程序路径后：

1. 运行候选程序
2. 读取 `temp/submission.json`
3. 检查 `density_vector` 维度与数值合法性
4. 独立计算柔度与可行性
5. 返回 `combined_score`、`valid` 与诊断信息

## 9. 评分定义

若可行：

```text
combined_score = baseline_uniform_compliance / compliance
```

若不可行：

```text
combined_score = 0
valid = 0
```

该定义保持“最小化柔度”的目标方向，同时满足“分数越高越好”。

## 10. 参考

- pyMOTO 官方仓库与拓扑优化示例
- SIMP 柔度最小化相关文献

