# TA (Taillard, 1993) Benchmark Family

## Background
Large and diverse industrial-style benchmark suite; standard stress-test family in JSSP research.

## Family profile

- Prefix: `ta`
- Instances: ta01-ta80
- Size range: 15x15 to 100x20
- Instances with unknown optimum in metadata: 22

## Environment dependencies

- Python: `>=3.10`
- Install shared dependencies from repository root:
  - `pip install -r JobShop/requirements.txt`
- `baseline/init.py`: Python standard library only.
- `verification/reference.py` and `verification/evaluate.py`:
  use the `job_shop_lib` Python package and OR-Tools (`ortools`).
  Benchmark instance data is vendored at `JobShop/data/benchmark_instances.json`, sourced from
  https://github.com/Pabloo22/job_shop_lib.git.

## Current directory structure

```
.
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   └── init.py
└── verification/
    ├── reference.py
    └── evaluate.py
```

## `evaluate.py` arguments

- `--instances`: optional explicit instance names.
  If omitted, all instances in this family are evaluated.
- `--max-instances`: optional cap on selected instances.
  The evaluator keeps the first N instances after optional `--instances` filtering.
- `--reference-time-limit`: time limit (seconds) per instance for reference solver.
  Default: `10.0`.

## Quick start

```bash
python JobShop/ta/baseline/init.py --max-instances 2
python JobShop/ta/verification/evaluate.py --max-instances 2 --reference-time-limit 5
```
