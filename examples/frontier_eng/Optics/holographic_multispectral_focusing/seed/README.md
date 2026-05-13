# Holographic H3: Multi-Wavelength Focusing/Splitting

## Background

A single diffractive element should operate across multiple wavelengths.
This task models spectral design requirements: each wavelength is steered to a designated region with controlled spectral power balance.

Application examples:

- color imaging optics,
- wavelength-division optical routing,
- chromatic compensation design.

## What the agent should modify

- Target file: `baseline/init.py`

## File structure

```text
task3_multispectral_focusing/
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
$PY benchmarks/Optics/holographic_multispectral_focusing/verification/evaluate.py
```

Artifacts are generated in `verification/artifacts/`.

## Oracle dependency

`verification/reference_solver.py` uses `slmsuite` as a third-party upper-bound oracle backend.
It combines WGS seeding with wavelength-specific independent fine-tuning in `torchoptics`.
