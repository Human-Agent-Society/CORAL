# Task 01 README

## Structure
- `baseline/init.py`: baseline algorithm (rule-based CST assignment, no optimizer)
- `verification/reference.py`: reference algorithm (stockpyl GSM tree DP)
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
cd tasks/tree_gsm_safety_stock
python verification/evaluate.py
```
