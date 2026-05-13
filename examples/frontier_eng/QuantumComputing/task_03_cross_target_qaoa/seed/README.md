# Task 03 README

This file focuses on run commands and directory layout.
For task definition (goal, I/O, scoring), see [TASK.md](TASK.md).

## Environment

```bash
pip install mqt.bench
```

## Run
From this task directory:

```bash
python verification/evaluate.py
```

Optional arguments:
- `--artifact-dir <path>`: custom output directory for generated QASM/PNG artifacts.
- `--json-out <path>`: save the evaluation report as JSON.

## File Structure
- `baseline/solve.py`: the evolve entrypoint; current baseline performs local rewrites, registers target-specific equivalences when needed, and then runs target-aware transpilation.
- `baseline/structural_optimizer.py`: local rewrite helper reused before and after target-aware transpilation.
- `verification/evaluate.py`: single evaluation entrypoint; includes candidate and `opt0..opt3` reference comparison for each target.
- `verification/utils.py`: task-local helper functions.
- `tests/case_*.json`: differentiated test cases.
- `TASK.md`: task details in English.
- `TASK_zh-CN.md`: task details in Chinese.
- `runs/`: generated artifacts for each evaluation run.

## Current Baseline
- Start with `optimize_by_local_rewrite(..., max_rounds=32)`.
- Register backend-specific equivalences for targets such as IonQ when needed.
- Choose transpile settings based on the target family, then run another local rewrite pass on the transpiled circuit.
