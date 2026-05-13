# ISCSO 2015 — 45 杆 2D 桁架尺寸 + 形状优化

## 快速开始

```bash
python scripts/init.py
python verification/evaluator.py scripts/init.py
```

## 基线

- **算法**: 应力比法
- **结果**: 2473.82 kg
- **人类最佳**: 1751.5 kg

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=StructuralOptimization/ISCSO2015`

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2015 algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=iscso2015`。
