# OpenFF Optimization Tasks

This directory separates each benchmark into two layers:

- Algorithm layer
  - `baseline/init.py`
  - Keeps the core optimization logic mostly independent from OpenFF, RDKit, and OpenMM
- Chemistry evaluation layer
  - `verification/evaluate.py`
  - Converts raw chemistry inputs into algorithm-friendly data
  - Runs the real evaluation with external libraries

## Metric Glossary

These tasks use three different kinds of reference values:

- `exact optimum`
  - The optimization problem for the current prepared instance is solved exactly
- `certified upper bound`
  - A score that no valid solution can exceed, even if the bound may be loose
- `known optimum`
  - A target score known by benchmark construction, not rediscovered online during evaluation

How they are used here:

- `weighted_parameter_coverage`
  - Solved exactly with MILP, so `exact_optimal_score` and `certified_upper_bound` are identical
- `diverse_conformer_portfolio`
  - Uses a valid but potentially loose `certified_upper_bound`
- `torsion_profile_fitting`
  - Uses a benchmark-defined `known_optimal_score`

## Current Starter Quality

With the current benchmark settings measured on `2026-03-16`:

- `weighted_parameter_coverage`
  - `63.067%` below the exact optimum
- `diverse_conformer_portfolio`
  - `58.777%` below the certified upper bound
- `torsion_profile_fitting`
  - `65.256%` below the known optimum

That means all three tasks currently preserve meaningful optimization headroom.

## Task Directories

- [weighted_parameter_coverage](weighted_parameter_coverage/)
  - Budgeted weighted coverage
- [diverse_conformer_portfolio](diverse_conformer_portfolio/)
  - Low-energy, high-diversity conformer selection
- [torsion_profile_fitting](torsion_profile_fitting/)
  - Continuous torsion-profile fitting

## Suggested Reading Order

1. Start with [README.md](README.md)
   - File layout, environment setup, and run commands
2. Then open a task-specific `Task.md`
   - Background, inputs, outputs, and scoring
3. Finally inspect `baseline/init.py`
   - The starter optimization logic
