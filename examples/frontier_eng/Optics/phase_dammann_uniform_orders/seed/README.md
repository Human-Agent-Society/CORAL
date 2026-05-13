# Phase DOE P3: Dammann Uniform Orders

## Background
Optimize binary transition positions for order uniformity and efficiency.

## Structure

```text
task03_dammann_uniform_orders/
  baseline/
    init.py
  verification/
    validate.py
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment Dependencies
- Use the shared environment file: `benchmarks/Optics/requirements.txt`
- Task03 runtime deps:
  - baseline: `numpy` + local `diffractio` source code in this repository
  - verification/oracle: `scipy`, `matplotlib`
  - local `diffractio` scalar modules additionally need `pandas`, `psutil`
- From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Run

```bash
PYTHONPATH=. python benchmarks/Optics/phase_dammann_uniform_orders/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_dammann_uniform_orders/verification/validate.py
```

Oracle = best-of(`SciPy-DE`, literature transition table).
