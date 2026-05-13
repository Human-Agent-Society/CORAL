# ISCSO 2023 — 284 杆 3D 桁架尺寸优化

## 快速开始

```bash
python scripts/init.py
python verification/evaluator.py scripts/init.py
```

## 基线

- **算法**: 离散应力比法
- **结果**: ~77813 kg
- **人类最佳**: 6619.66 kg

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=StructuralOptimization/ISCSO2023`

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2023 algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=iscso2023`。
