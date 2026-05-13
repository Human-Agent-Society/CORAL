# SnAr Multiobjective

This task comes from the SUMMIT `SnarBenchmark`, a continuous-flow reaction benchmark where we want high productivity without generating excessive waste.

Use this directory when you want a realistic continuous black-box optimization problem with a fixed small budget and two competing objectives.

Current implementations:

- `baseline/solution.py`: adaptive random scalarization. It rotates among several objective weights, evaluates either a random point or a mutation of the current scalarized incumbent, and keeps improving a simple Pareto proxy without using an external optimizer.
- `verification/reference.py`: weighted SUMMIT Bayesian optimization. It splits the budget across several scalarization weights, runs `SOBO` with `MultitoSingleObjective` for each weight, and merges the observed points into one Pareto set.

Current folder structure:

- `task.py`: bounds, benchmark construction, scalarization helper, and score definition
- `Task.md`: full task definition
- `Task_zh-CN.md`: Chinese task definition
- `baseline/solution.py`: simple adaptive random search
- `verification/reference.py`: SUMMIT-based reference search
- `verification/evaluate.py`: compares baseline, reference, and score gap
