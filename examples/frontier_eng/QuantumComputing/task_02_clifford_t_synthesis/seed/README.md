# 02

For task definition (goal, I/O, scoring), see [TASK.md](TASK.md).

## Environment
Use the requested interpreter:

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
- `baseline/solve.py`: the evolve entrypoint; current baseline combines local rewrites with a high-effort `clifford+t` transpilation pass.
- `baseline/structural_optimizer.py`: local rewrite helper used before and after transpilation.
- `verification/evaluate.py`: single evaluation entrypoint; includes candidate and `opt0..opt3` reference comparison.
- `verification/utils.py`: task-local helper functions.
- `tests/case_*.json`: differentiated test cases.
- `TASK.md`: task details in English.
- `TASK_zh-CN.md`: task details in Chinese.
- `runs/`: generated artifacts for each evaluation run.

## Current Baseline
- First apply `optimize_by_local_rewrite(..., max_rounds=20)`.
- Then transpile aggressively at `optimization_level=3` with an explicit `clifford+t` basis.
- Finally run another local rewrite pass on the transpiled circuit.
