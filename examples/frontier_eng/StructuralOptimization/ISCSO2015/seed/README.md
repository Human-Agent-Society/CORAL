# ISCSO 2015 — 45-Bar 2D Truss Size + Shape Optimization

## Quick Start

```bash
python scripts/init.py
python verification/evaluator.py scripts/init.py
```

## Baseline

- **Algorithm**: Stress Ratio Method
- **Result**: 2473.82 kg
- **Human best**: 1751.5 kg

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=StructuralOptimization/ISCSO2015`

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2015 algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=iscso2015`.
