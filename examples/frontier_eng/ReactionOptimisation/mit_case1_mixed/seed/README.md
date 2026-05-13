# MIT Case 1 Mixed

This task comes from the SUMMIT `MIT_case1` benchmark. It is a compact mixed-variable optimization problem: three continuous process variables plus one categorical catalyst choice.

Use this task when you want to practice black-box optimization with both discrete and continuous decisions under a very small experimental budget.

Current implementations:

- `baseline/solution.py`: mixed random plus local search. It mostly alternates between random exploration and local perturbation around the best observed yield, without using any off-the-shelf optimizer.
- `verification/reference.py`: direct SUMMIT `SOBO` on the mixed domain. The categorical catalyst variable is left inside the SUMMIT domain, and `SOBO` handles the sequential suggestion loop end to end.

Current folder structure:

- `task.py`: benchmark construction, bounds, mutation helpers, and score definition
- `Task.md`: full task definition
- `Task_zh-CN.md`: Chinese task definition
- `baseline/solution.py`: simple mixed random/local search
- `verification/reference.py`: SUMMIT-based reference optimizer
- `verification/evaluate.py`: runs and scores baseline and reference
