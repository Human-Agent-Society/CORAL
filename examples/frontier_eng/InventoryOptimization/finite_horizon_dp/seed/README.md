# Task 04 README

## Structure
- `baseline/init.py`: baseline algorithm (manual moment-based time-varying policy)
- `verification/reference.py`: reference algorithm (stockpyl finite-horizon DP)
- `verification/evaluate.py`: runs both algorithms, computes scores, compares results
- `output/`: generated outputs
  - `baseline_result.json`
  - `reference_result.json`
  - `comparison.json`
- `Task.md` / `Task_zh-CN.md`: full task description and scoring design

## Environment
Use the shared setup in `tasks/README.md` (Conda env `stock`).

## Run
```bash
cd tasks/finite_horizon_dp
python verification/evaluate.py
```
