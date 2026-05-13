# Reizman Suzuki Pareto

This task comes from a pretrained SUMMIT emulator for Suzuki cross-coupling experiments. It mixes a categorical catalyst choice with continuous operating conditions and uses a two-objective score.

Use this task when you want a more engineering-flavored Pareto optimization problem where category choice matters a lot.

Current implementations:

- `baseline/solution.py`: pure random search. Every step independently samples a catalyst and continuous operating conditions, so it acts as a simple lower bound.
- `verification/reference.py`: two-stage screened SUMMIT search. It first evaluates all catalysts once at a fixed screening condition, then chooses promising catalyst/weight combinations and runs fixed-catalyst continuous `SOBO` in the reduced three-variable subspace.

Current folder structure:

- `task.py`: benchmark construction, bounds, scalarization helper, and score definition
- `Task.md`: full task definition
- `Task_zh-CN.md`: Chinese task definition
- `baseline/solution.py`: simple pure random baseline
- `verification/reference.py`: screened fixed-catalyst SUMMIT reference
- `verification/evaluate.py`: runs both methods and reports the score gap
