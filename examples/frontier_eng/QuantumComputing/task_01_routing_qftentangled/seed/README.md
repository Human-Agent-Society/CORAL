# 01

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
- `baseline/solve.py`: the evolve entrypoint; current baseline uses local rewrites plus target-aware multi-seed transpile search over several layout/routing settings.
- `baseline/structural_optimizer.py`: local rewrite helper reused as a preprocessing step before transpile search.
- `verification/evaluate.py`: single evaluation entrypoint; includes candidate and `opt0..opt3` reference comparison.
- `verification/utils.py`: task-local helper functions (case loading, metrics, artifact saving, dynamic solver loading).
- `tests/case_*.json`: differentiated test cases.
- `TASK.md`: task details in English.
- `TASK_zh-CN.md`: task details in Chinese.
- `runs/`: generated artifacts for each evaluation run.

## Current Baseline
- Start from `optimize_by_local_rewrite(...)` to remove obvious local structure.
- If a `Target` is available, run several `transpile(...)` configurations across multiple seeds and keep the best circuit by a two-qubit-gate-plus-depth cost.
