# Topology Optimization

Optimize the material distribution of a 2D MBB beam using the SIMP formulation.
This benchmark minimizes structural compliance under a fixed volume fraction constraint using a density-based finite-element model.

## File Structure

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

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run the Baseline Solver

```bash
cd benchmarks/StructuralOptimization/TopologyOptimization
python scripts/init.py
# Outputs: temp/submission.json
```

### 3. Evaluate a Candidate Program

```bash
cd benchmarks/StructuralOptimization/TopologyOptimization
python verification/evaluator.py scripts/init.py
```

## Submission Format

The candidate program must write `temp/submission.json` containing:

```json
{
  "benchmark_id": "topology_optimization",
  "density_vector": [0.5, 0.5, 0.5],
  "nelx": 60,
  "nely": 20
}
```

`density_vector` is a flattened density field of length `nelx * nely`.

## Task Summary

- **Problem**: 2D MBB beam topology optimization
- **Mesh**: `60 x 20` quadrilateral elements
- **Design dimension**: `1200`
- **Objective**: minimize compliance
- **Volume constraint**: average density must be at most `0.5`
- **Penalization**: `penal = 3.0`
- **Filter radius**: `rmin = 1.5`
- **Boundary condition**: MBB half-symmetry
- **Load**: downward unit load at the top-left node

## Scoring

- Feasible submissions receive score equal to structural compliance, where lower is better.
- Infeasible submissions receive an invalid result.
- In `frontier_eval`, feasible runs are converted to `combined_score = -compliance`, so higher is better there.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=StructuralOptimization/TopologyOptimization`

```bash
python -m frontier_eval \
task=unified task.benchmark=StructuralOptimization/TopologyOptimization \
algorithm.iterations=10
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=topology_optimization`.
