# DTLZ2 Pareto

This task wraps the SUMMIT `DTLZ2` benchmark, a synthetic multi-objective problem with a known theoretical Pareto front.

It is less “chemical” than the other tasks, but it is very useful for debugging optimization code because the score has an exact theoretical ceiling.

Current implementations:

- `baseline/solution.py`: random scalarization with local mutation. It rotates through several scalarization weights, keeps a scalarized incumbent, and perturbs that incumbent to search nearby regions.
- `verification/reference.py`: split-budget SUMMIT scalarized Bayesian optimization. It runs `SOBO` under several scalarization weights and merges all discovered points before scoring.

Current folder structure:

- `task.py`: benchmark construction, candidate helpers, and exact score definition
- `Task.md`: full task definition
- `Task_zh-CN.md`: Chinese task definition
- `baseline/solution.py`: simple continuous random search baseline
- `verification/reference.py`: SUMMIT-based scalarized reference search
- `verification/evaluate.py`: compares baseline, reference, and theoretical limit
