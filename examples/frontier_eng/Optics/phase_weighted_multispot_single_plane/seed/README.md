# Phase DOE P1: Hard Weighted Multi-Spot

## Background
Phase-only Fourier holography for a dense weighted spot field (7x7 spots, strongly non-uniform target power).
Primary task score is `score` in `[0, 1]` (higher is better). Verifier also emits `score_pct` as a compatibility field.

## Structure

```text
task01_weighted_multispot_single_plane/
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
- Task01 runtime deps: `numpy`, `matplotlib`, `slmsuite`
- From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Run

```bash
PYTHONPATH=. python benchmarks/Optics/phase_weighted_multispot_single_plane/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_weighted_multispot_single_plane/verification/validate.py
```

Oracle: `slmsuite` `WGS-Kim`.
