# Phase DOE P2: Hard Fourier Pattern Holography

## Background
Phase-only reconstruction of a sparse high-contrast target with keep-out dark regions.

## Structure

```text
task02_fourier_pattern_holography/
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
- Task02 runtime deps: `numpy`, `matplotlib`, `slmsuite`
- From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Run

```bash
PYTHONPATH=. python benchmarks/Optics/phase_fourier_pattern_holography/baseline/init.py
PYTHONPATH=. python benchmarks/Optics/phase_fourier_pattern_holography/verification/validate.py
```

Oracle: `slmsuite` `WGS-Kim`.
