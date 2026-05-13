# Fiber F4 Specification: Spectrum Packing with Guard Bands

## Background

Elastic optical networking can be modeled as packing variable-width requests into a finite 1D spectrum grid.

Each user requests a number of contiguous spectrum slots.

Constraints:

- allocated blocks cannot overlap,
- adjacent blocks require guard slots,
- total spectrum is limited.

This is close to constrained bin packing / interval scheduling with additional communication-quality implications.

## What You Need To Do

Implement one function:

- editable file: `baseline/init.py`
- function to evolve: `pack_spectrum(...)`

`verification/` scripts and oracle are read-only references.

## Function Interface

```python
def pack_spectrum(user_demand_slots, n_slots, guard_slots=1, seed=0):
    return {"alloc": np.ndarray}  # shape (U, 2)
```

Allocation encoding per user `i`:

- assigned: `(start, width)`
- not assigned: `(-1, 0)`



Inputs:

- `user_demand_slots`: required contiguous slot width per user.
- `n_slots`: total slot count in the spectrum.
- `guard_slots`: required empty gap around allocated intervals.

Output:

- `alloc[i] = (start, width)` if user is accepted.
- `alloc[i] = (-1, 0)` if user is rejected.

## Hard Validity Constraints

`verification` checks geometry strictly:

1. `alloc.shape == (U, 2)`
2. for assigned users: `start >= 0`, `width > 0`, `start + width <= n_slots`
3. assigned `width` must equal requested `user_demand_slots[i]`
4. no overlap between allocated blocks
5. guard-band constraint must hold between any two allocations

Invalid geometry makes final result invalid regardless of score.

## Verification Pipeline and Metrics

Scenario (`seed=99`) is deliberately hard:

- bimodal demands: many small requests + some large requests
- total slots: `68`
- guard slots: `1`

Besides geometric metrics, verification includes a BER proxy:

- users have base SNR,
- nearby packed allocations create adjacency interference,
- effective SNR is converted to BER by OptiCommPy `theoryBER`.

Metrics:

- `acceptance_ratio`
- `utilization`
- `compactness` (inverse of free-block count)
- `ber_pass_ratio`

Score:

`0.80*acceptance + 0.05*utilization + 0.05*compactness + 0.10*ber_pass`

Validity thresholds:

- `acceptance_ratio >= 0.25`
- `ber_pass_ratio >= 0.80`
- geometry must be valid

## Baseline (Simple, Low Dependency)

`baseline/init.py` uses First-Fit Decreasing:

1. sort users by descending demand width,
2. place each request at first feasible position,
3. reject if no feasible position.

Simple and deterministic, but can create fragmentation and poor acceptance.

## Oracle (Stronger Reference)

`verification/oracle.py` supports multiple stronger methods:

- `heuristic`: small-demand-first + best-fit with fragmentation-aware placement
- `hybrid`: local search over user order + best-fit packing
- `exact_geometry`: OR-Tools CP-SAT exact solve for geometry objective
- `auto`: compare available strategies by proxy score and pick best

Important note:

- full verification score includes BER proxy,
- `exact_geometry` is exact for geometry objective, not necessarily exact for final score,
- in practice `hybrid` can outperform `exact_geometry` on final score.

## Files in `verification/outputs/`

Each run generates:

- `summary.json`
- `task4_verification.png`

`summary.json`:

- `candidate`: full evaluated metrics and allocation
- `oracle`: same fields for reference
- `oracle_meta`: which oracle backend was used
- `score_gap_oracle_minus_candidate`: performance gap

`task4_verification.png`:

- top panel: candidate spectrum occupancy by user
- bottom panel: oracle spectrum occupancy by user

This plot is useful for visually diagnosing fragmentation and acceptance behavior.

## Why This Task Is Engineering-Relevant

The objective aligns with practical spectrum economics:

- serve more users (`acceptance`) as the primary KPI,
- keep packing efficient (`utilization`, `compactness`),
- avoid placements that degrade quality too much (`ber_pass`).

This reflects real tradeoffs in elastic optical resource orchestration.
