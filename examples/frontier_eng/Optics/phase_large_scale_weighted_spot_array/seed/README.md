# Phase DOE P4: Large-Scale Weighted Spot Array

## Background
Optimize phase-only hologram for dense weighted multi-spot output.

## Structure

```text
task04_large_scale_spot_array/
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
- Task04 runtime deps: `numpy`, `matplotlib`, `slmsuite`
- From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Run

```bash
PYTHONPATH=. python benchmarks/Optics/phase_large_scale_weighted_spot_array/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_large_scale_weighted_spot_array/verification/validate.py
```

Oracle: `slmsuite` `WGS-Kim`.
