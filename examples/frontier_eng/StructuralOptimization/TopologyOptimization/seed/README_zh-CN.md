# 拓扑优化

使用 SIMP 公式优化二维 MBB 梁的材料分布。
该基准通过基于密度的有限元模型，在固定体积分数约束下最小化结构柔顺度。

## 文件结构

```text
TopologyOptimization/
├── README.md
├── Task.md
├── references/
│   └── problem_config.json
├── scripts/
│   └── init.py
└── verification/
    ├── evaluator.py
    └── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线求解器

```bash
cd benchmarks/StructuralOptimization/TopologyOptimization
python scripts/init.py
# 输出: temp/submission.json
```

### 3. 评测候选程序

```bash
cd benchmarks/StructuralOptimization/TopologyOptimization
python verification/evaluator.py scripts/init.py
```

## 提交格式

候选程序必须写出 `temp/submission.json`，内容如下：

```json
{
  "benchmark_id": "topology_optimization",
  "density_vector": [0.5, 0.5, 0.5],
  "nelx": 60,
  "nely": 20
}
```

`density_vector` 是长度为 `nelx * nely` 的展平密度场。

## 任务摘要

- **问题**: 二维 MBB 梁拓扑优化
- **网格**: `60 x 20` 四边形单元
- **设计维度**: `1200`
- **目标**: 最小化柔顺度
- **体积约束**: 平均密度不超过 `0.5`
- **惩罚参数**: `penal = 3.0`
- **滤波半径**: `rmin = 1.5`
- **边界条件**: MBB 半对称边界
- **载荷**: 左上节点施加向下单位载荷

## 评分

- 可行提交的分数等于结构柔顺度，越低越好。
- 不可行提交返回无效结果。
- 在 `frontier_eval` 中，可行运行会转换为 `combined_score = -compliance`，因此分数越高越好。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=StructuralOptimization/TopologyOptimization`

```bash
python -m frontier_eval \
task=unified task.benchmark=StructuralOptimization/TopologyOptimization \
algorithm.iterations=10
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=topology_optimization`。
