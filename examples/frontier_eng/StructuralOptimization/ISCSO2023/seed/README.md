# ISCSO 2023 — 284-Member 3D Truss Sizing Optimization

## Quick Start

```bash
python scripts/init.py
python verification/evaluator.py scripts/init.py
```

## Baseline

- **Algorithm**: Discrete Stress Ratio Method
- **Result**: ~77813 kg
- **Human best**: 6619.66 kg

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=StructuralOptimization/ISCSO2023`

```bash
python -m frontier_eval task=unified task.benchmark=StructuralOptimization/ISCSO2023 algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=iscso2023`.
