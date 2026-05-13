# Optics Benchmark Suite (16 Tasks)

This directory now contains a **flat 16-task optics benchmark** with unified entry docs and shared dependencies.

## What all 16 tasks share

All tasks follow the same engineering benchmark pattern:

1. Edit exactly one baseline solver/controller file per task.
2. Keep verification/oracle logic read-only.
3. Optimize a measurable engineering objective under physical or system constraints.
4. Produce reproducible metrics (JSON) and visual artifacts.

Across the suite, tasks cover four real-world optical optimization domains:

- adaptive wavefront correction and robust AO control,
- phase-only DOE/holography synthesis,
- optical communication resource scheduling,
- differentiable diffractive optics design (space/depth/spectrum/polarization).

## Naming convention after restructuring

The previous 4 outer folders were removed. Tasks are renamed and moved directly under `benchmarks/Optics` with semantic prefixes:

- `adaptive_*`: adaptive optics control tasks
- `phase_*`: phase-only DOE tasks
- `fiber_*`: optical fiber communication scheduling tasks
- `holographic_*`: differentiable holographic design tasks

## Task differences (all 16)

| Task Folder | Main Optimization Focus | Typical Constraint / Challenge |
|---|---|---|
| `adaptive_constrained_dm_control` | bounded DM command quality | actuator voltage bounds + delayed/noisy sensing |
| `adaptive_temporal_smooth_control` | temporal smoothness vs correction quality | jitter/lag/rate-like dynamics |
| `adaptive_energy_aware_control` | correction quality vs command energy | sparse/low-energy control tradeoff |
| `adaptive_fault_tolerant_fusion` | robust multi-WFS fusion | severe channel corruption/outliers |
| `phase_weighted_multispot_single_plane` | weighted multi-spot power split | non-convex phase-only mapping |
| `phase_fourier_pattern_holography` | sparse high-contrast pattern reconstruction | fidelity vs dark-zone leakage |
| `phase_dammann_uniform_orders` | Dammann transition parameter optimization | order uniformity vs diffraction efficiency |
| `phase_large_scale_weighted_spot_array` | large-scale (8x8) weighted spot allocation | many-target stability |
| `fiber_wdm_channel_power_allocation` | user-channel assignment + launch power | interference + total power budget |
| `fiber_mcs_power_scheduling` | joint `(MCS, power)` selection | multiple-choice budgeted scheduling |
| `fiber_dsp_mode_scheduling` | EDC/DBP receiver mode scheduling | latency budget and utility tradeoff |
| `fiber_guardband_spectrum_packing` | interval packing in spectrum grid | non-overlap + guard-band geometry |
| `holographic_multifocus_power_ratio` | multi-focus ratio control on one plane | spot quality vs ratio accuracy |
| `holographic_multiplane_focusing` | one design for multiple depth planes | cross-plane consistency |
| `holographic_multispectral_focusing` | per-wavelength routing + spectral ratio | wavelength coupling/crosstalk |
| `holographic_polarization_multiplexing` | channel-separated polarization patterns | inter-polarization leakage suppression |

## Score and output notes

Scoring APIs differ slightly by task family (for example `score_0_to_1_higher_is_better` or `score_pct`), but every task is configured as **higher-is-better** in its own verifier output.

## Unified dependencies

Dependency reconciliation across the previous four task groups shows no hard version conflict for a single shared environment.

Use:

```bash
python -m pip install -r benchmarks/Optics/requirements.txt
```

## Quick run examples

```bash
python benchmarks/Optics/adaptive_constrained_dm_control/verification/evaluate.py
python benchmarks/Optics/phase_weighted_multispot_single_plane/verification/validate.py
python benchmarks/Optics/fiber_wdm_channel_power_allocation/verification/run_validation.py
python benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py
```

## Frontier Eval (Unified)

All 16 Optics tasks are now integrated with `frontier_eval` through `task=unified` metadata under each task folder (`benchmarks/Optics/<task>/frontier_eval`).

Example:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Optics/phase_weighted_multispot_single_plane \
  algorithm=openevolve \
  algorithm.iterations=0
```

Replace `task.benchmark` with any task folder listed in this README.

## Timeout and Runtime Reference

In `frontier_eval`, the default per-evaluation timeout is `300s`.

- OpenEvolve: `algorithm.oe.evaluator.timeout=300` (default)
- ABMCTS / ShinkaEvolve: `algorithm.evaluator_timeout_s=300` (default)

If a task times out (especially `holographic_*`), increase the timeout:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Optics/holographic_multifocus_power_ratio \
  algorithm=openevolve \
  algorithm.iterations=0 \
  algorithm.oe.evaluator.timeout=600
```

Approximate runtime (single evaluation, `algorithm.iterations=0`, CPU):

| Task Family | Approx Runtime |
|---|---|
| `adaptive_*` | ~`6-15s` |
| `phase_*` | ~`8-20s` |
| `fiber_*` | ~`7-20s` |
| `holographic_*` | ~`170-260s` (can exceed `300s` on slower CPUs) |

Representative measured tasks:
- `adaptive_constrained_dm_control`: ~`6.3s`
- `phase_weighted_multispot_single_plane`: ~`9.3s`
- `fiber_wdm_channel_power_allocation`: ~`7.2s`
- `holographic_multifocus_power_ratio`: ~`184.7s`

## Old-to-new folder mapping

| Old Path | New Path |
|---|---|
| `AoTools/task1_constrained_dm_control` | `adaptive_constrained_dm_control` |
| `AoTools/task2_temporal_smooth_control` | `adaptive_temporal_smooth_control` |
| `AoTools/task3_energy_aware_control` | `adaptive_energy_aware_control` |
| `AoTools/task4_fault_tolerant_fusion` | `adaptive_fault_tolerant_fusion` |
| `diffractio/task01_weighted_multispot_single_plane` | `phase_weighted_multispot_single_plane` |
| `diffractio/task02_fourier_pattern_holography` | `phase_fourier_pattern_holography` |
| `diffractio/task03_dammann_uniform_orders` | `phase_dammann_uniform_orders` |
| `diffractio/task04_large_scale_spot_array` | `phase_large_scale_weighted_spot_array` |
| `OptiCommpy/task1_wdm_channel_power` | `fiber_wdm_channel_power_allocation` |
| `OptiCommpy/task2_mcs_power` | `fiber_mcs_power_scheduling` |
| `OptiCommpy/task3_dsp_mode` | `fiber_dsp_mode_scheduling` |
| `OptiCommpy/task4_spectrum_packing` | `fiber_guardband_spectrum_packing` |
| `torchoptics/task1_multifocus_power_ratio` | `holographic_multifocus_power_ratio` |
| `torchoptics/task2_multiplane_focusing` | `holographic_multiplane_focusing` |
| `torchoptics/task3_multispectral_focusing` | `holographic_multispectral_focusing` |
| `torchoptics/task4_polarization_multiplexing` | `holographic_polarization_multiplexing` |
