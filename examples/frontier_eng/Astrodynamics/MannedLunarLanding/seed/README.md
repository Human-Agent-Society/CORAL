# Manned Lunar Landing (Astrodynamics)

This folder contains the assignment specification, a baseline trajectory script that generates `results.txt`, and validator programs (MATLAB and Octave) that check the file against the mission constraints.

## Key Files and Roles

- `Task.md`
  - Assignment specification: mission background, model definitions, constraints, event codes, and `results.txt` format.

- `scripts/init.py`
  - Baseline CR3BP trajectory generator (Earth departure → lunar arrival/LOI → lunar stay → TEI → Earth return).
  - Computes mass budget and writes `results.txt` in the current working directory.
  - Includes placeholders for an L1 Lyapunov resupply ship model (`SupplyShip` is TODO).

- `eval/error_checking_program.m`
  - MATLAB validator that reads `results.txt` and checks:
    - event completeness and ordering
    - time monotonicity and total duration
    - departure/arrival orbit constraints
    - maneuver Δv and fuel bookkeeping
    - coast-arc propagation accuracy and altitude bounds
    - optional resupply rendezvous constraints
    - return conditions and fuel limit
  - Writes an `outputlog.txt` report and plots the trajectory.

- `eval/aerodynamics_check_octave_full.m`
  - Octave-compatible version of the validator (same checks, adjusted `findpeaks` usage).
  - Writes `outputlog.txt` for inspection.

## Generated Artifacts

- `results.txt`
  - Output file produced by `scripts/init.py` (or your own solver). Must follow the format in `Task.md`.

- `outputlog.txt`
  - Validation report produced by the MATLAB/Octave checkers.

## Typical Workflow

If Octave is not installed yet, you can bootstrap it with:

```bash
bash scripts/bootstrap/install_host_deps.sh --octave
```

1. Implement or modify a solver to generate `results.txt` (see `scripts/init.py`).
2. Run the MATLAB or Octave checker in `eval/` to validate the file.
3. Iterate until all checks pass and the payload is maximized.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Astrodynamics/MannedLunarLanding`

```bash
python -m frontier_eval task=unified task.benchmark=Astrodynamics/MannedLunarLanding algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=manned_lunar_landing`.
