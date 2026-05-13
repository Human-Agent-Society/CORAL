# Holographic H2: Multi-Plane Focusing

## Background

A single diffractive optical stack often needs to satisfy multiple depth planes.
This task models 3D optical control: focus patterns must be formed at multiple z planes.

Application examples:

- 3D optical trapping,
- volumetric laser processing,
- depth-multiplexed optical projection.

## What the agent should modify

- Target file: `baseline/init.py`

## File structure

```text
task2_multiplane_focusing/
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
$PY benchmarks/Optics/holographic_multiplane_focusing/verification/evaluate.py
```

Artifacts are generated in `verification/artifacts/`.

## Oracle dependency

`verification/reference_solver.py` uses `slmsuite` as a third-party oracle backend.
