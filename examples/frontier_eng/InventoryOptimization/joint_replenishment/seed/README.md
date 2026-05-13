# Task 03 README

## Structure
- `baseline/init.py`: baseline algorithm (fixed-cycle + demand-bucket multiples)
- `verification/reference.py`: reference algorithm (stockpyl Silver JRP heuristic)
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
cd tasks/joint_replenishment
python verification/evaluate.py
```
