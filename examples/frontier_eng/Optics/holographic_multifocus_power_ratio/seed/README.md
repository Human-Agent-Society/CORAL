# Holographic H1: Multifocus Power-Ratio Control

## Background

This task models a practical diffractive optical element (DOE) design problem:
create multiple focal spots at specified positions while enforcing target relative powers.

Typical applications include:

- parallel laser processing,
- optical tweezers with multi-trap control,
- multi-channel free-space optical coupling.

## What the agent should modify

- Target file: `baseline/init.py`
- Other files should be considered read-only in challenge setup.

## File structure

```text
task1_multifocus_power_ratio/
  baseline/
    init.py
  verification/
    evaluate.py
    reference_solver.py
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment dependencies

Recommended interpreter:

```bash
python
```

Shared task requirements file:

- `benchmarks/Optics/requirements.txt`

Install example (from repository root):

```bash
PY=python3
$PY -m pip install -r benchmarks/Optics/requirements.txt
$PY -m pip install -e .
```

If you only run baseline logic and skip oracle, you may remove `slmsuite`/`scipy` from that requirements file.

## How to run

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py
```

Optional arguments:

- `--device cpu|cuda`
- `--baseline-steps N`
- `--reference-steps N`
- `--seed N`

## Outputs

The evaluator writes artifacts to:

- `verification/artifacts/summary.json`
- `verification/artifacts/intensity_maps.png`
- `verification/artifacts/ratios_and_losses.png`

## Oracle dependency

`verification/reference_solver.py` uses `slmsuite` as a third-party oracle backend.
