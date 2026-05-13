# Industrial Context And Modeling Notes

This benchmark is intentionally reduced-order, but the task structure is chosen to match how industrial fast-charging problems are usually framed.

## Real Engineering Requirement

In production charging systems, the protocol is rarely optimized for speed alone. Engineers usually care about all of the following at the same time:

- `charge-time target`: for example reaching `80%` SOC from a low-SOC arrival state.
- `hard safety limits`: terminal voltage, cell temperature, and emergency cutoffs.
- `plating avoidance`: aggressive current at low temperature or high SOC can push the anode potential into a dangerous region.
- `lifetime impact`: repeated fast charging can accelerate SEI growth, lithium inventory loss, and impedance rise.
- `implementation simplicity`: many production chargers still prefer schedules that can be represented as staged CC logic, lookup tables, or MPC policies over low-order models.

That is why this benchmark asks the user to optimize a staged constant-current profile rather than a fully free control waveform.

## Common Modeling Stack In Industry

### Equivalent-circuit models

ECM-based models are common in battery-management systems because they are easy to calibrate and cheap enough for embedded control. A typical model includes:

- OCV as a function of SOC,
- ohmic resistance,
- one or more RC polarization branches,
- optional thermal coupling.

This class of model is widely used for state estimation, online current limiting, and supervisory charging logic.

### Reduced electrochemical models

When engineers need to reason about diffusion limitation or plating tendency, they often move to reduced electrochemical models such as:

- single-particle models,
- single-particle models with electrolyte dynamics,
- hybrid electrochemical-equivalent-circuit models.

These models are still tractable enough for optimization or offline protocol search, but they preserve more physically meaningful internal states.

### High-fidelity porous-electrode models

Full P2D / DFN-class models are valuable for:

- mechanism studies,
- design-space exploration,
- offline protocol validation,
- generating synthetic labels for simpler controllers.

They are less common inside embedded production loops because they are too expensive and too parameter-sensitive for many real-time deployment settings.

## How This Benchmark Maps To That Stack

The evaluator uses a deterministic surrogate with these pieces:

- nonlinear OCV curve,
- SOC- and temperature-dependent resistance,
- polarization state,
- concentration-gradient proxy,
- lumped thermal balance,
- plating-risk proxy,
- aging-loss surrogate.

This is not meant to be a chemistry-accurate digital twin. It is meant to preserve the most important optimization tensions:

- pushing current early is good for time,
- holding high current too deep into SOC increases voltage stress,
- high current and concentration overpotential increase plating tendency,
- extra heat and plating translate into long-term cost.

## User-Configurable Parameters

All battery and evaluation parameters live in:

- `references/battery_config.json`

This file is intended as the main customization point. Users can change:

- battery capacity,
- initial / target SOC,
- ambient temperature,
- voltage and temperature limits,
- simulation horizon,
- current bounds,
- reduced-model coefficients,
- score weights.

The current values are example parameters for a generic `3.0 Ah` lithium-ion cell. They are not presented as a validated commercial product dataset.

## Notes On The Current Surrogate

### OCV block

The OCV relation uses a smooth nonlinear function so that:

- low-to-mid SOC charging stays permissive,
- voltage rise becomes sharper at high SOC,
- staged current reduction near the end becomes meaningful.

### Resistance and polarization

The resistance and polarization terms are shaped so that:

- low-SOC and high-SOC regions are more difficult,
- sustained high current produces extra voltage rise,
- temperature interacts with resistance in a physically reasonable direction.

### Plating proxy

Real plating depends on local anode overpotential, temperature, diffusion limitation, particle gradients, and cell design. Here it is represented with a lower-order margin term built from:

- SOC,
- current,
- concentration-gradient proxy,
- cold-temperature penalty.

This is a proxy, not a direct electrochemical plating model, but it creates the same qualitative behavior the optimizer must handle.

### Aging proxy

The aging term combines:

- current-driven stress,
- temperature acceleration,
- an additional penalty coupled to plating severity.

This gives the benchmark a practical notion of "fast but abusive" versus "fast and controlled".

## Why The Task Is Kept Deterministic

The evaluator is deterministic because benchmarking needs:

- repeatable scoring,
- low variance across runs,
- fast local verification,
- compatibility with evolutionary search and batch evaluation.

A stochastic uncertainty layer can be added later, but for a first benchmark contribution deterministic evaluation is the right tradeoff.

## Suggested Extension Directions

If this task is extended in the future, the most natural upgrades are:

- multiple ambient-temperature cases,
- CC-CV tail handling,
- pack-level thermal constraints,
- parameter-set sweeps over multiple cell types,
- degradation-aware robustness rather than single-condition optimization.

## Sources Used For Grounding

- [Nature Energy (2019): Challenges and opportunities towards fast-charging battery materials](https://www.nature.com/articles/s41560-019-0405-3)
- [Nature Communications (2023): Extreme fast charging of commercial Li-ion batteries via combined thermal switching and self-heating approaches](https://www.nature.com/articles/s41467-023-38823-9)
- [Nature Energy (2023): Quantifying lithium plating for fast-charge protocol design](https://www.nature.com/articles/s41560-023-01194-y)
- [OSTI (2015): Lithium-ion battery cell-level control using constrained model predictive control and equivalent circuit models](https://www.osti.gov/biblio/1211079)
- [Journal of Energy Storage (2024): A novel hybrid electrochemical equivalent circuit model for online battery management systems](https://www.sciencedirect.com/science/article/pii/S2352152X24027282)
- [Journal of Energy Storage (2021): Fast charging lithium-ion battery formation based on simulations with an electrode equivalent circuit model](https://www.sciencedirect.com/science/article/abs/pii/S2352152X21001080)

## Benchmark Interpretation

This benchmark should be understood as:

- a charging-policy optimization task,
- a reduced-order engineering benchmark,
- not a full electrochemical solver benchmark,
- not a battery-parameter identification benchmark.

The main challenge is to discover a charging profile that exploits the safe region efficiently without relying on unrealistic aggressive current all the way to the target SOC.
