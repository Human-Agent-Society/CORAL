# SPMe-T-Aging Modeling Notes

This task is designed around a control-oriented model hierarchy that sits between simple equivalent-circuit models and full porous-electrode solvers.

## Why This Task Exists

Pure ECM-based fast-charge tasks are cheap, but they cannot represent the most important internal fast-charging limits:

- solid-state surface saturation,
- electrolyte polarization,
- plating-risk boundary movement,
- temperature-driven kinetic changes,
- SEI-growth acceleration under stress.

Full P2D / DFN models capture those effects much better, but they are usually too expensive for large-scale search, reinforcement learning, MPC benchmarking, or AI-agent evolutionary loops.

This benchmark therefore targets the middle layer:

- `SPMe-style electrochemical reduction`
- `lumped thermal coupling`
- `semi-empirical plating and aging surrogates`

## State Variables

The evaluator tracks:

- negative average stoichiometry,
- negative surface stoichiometry deviation,
- positive average stoichiometry,
- positive surface stoichiometry deviation,
- electrolyte polarization state,
- lumped temperature,
- cumulative plating-loss surrogate,
- cumulative SEI-aging surrogate.

These states are chosen because they correspond directly to the key fast-charge failure modes.

## Reduced Electrochemical Structure

### 1. Solid-state dynamics

The model uses a reduced single-particle interpretation:

- average stoichiometry moves with charge throughput,
- surface deviation evolves with a first-order relaxation proxy,
- surface stoichiometry determines OCV and kinetic stress.

This preserves the control-relevant effect that high current can temporarily push the surface state much harder than the bulk state.

### 2. Electrolyte polarization

A separate electrolyte polarization state is included so that:

- large current raises electrolyte overpotential,
- voltage can increase before the solid particles fully saturate,
- plating risk becomes more severe under high-current concentration stress.

This is the main reason the task is more realistic than a pure solid-state or ECM-only formulation.

### 3. Kinetic overpotential

The evaluator uses Butler-Volmer-inspired asinh overpotential proxies with exchange-current surrogates that depend on:

- electrode surface stoichiometry,
- temperature,
- electrolyte polarization factor.

That makes high-current charging more expensive in a physically meaningful way even before hard limits are hit.

## Thermal Coupling

The task uses a lumped thermal model:

- irreversible heat comes from voltage loss relative to OCV,
- reversible heat is approximated through an entropic term,
- heat is rejected to ambient through a first-order cooling term.

Temperature feeds back into the electrochemical states through Arrhenius-style multipliers. In this task it affects:

- solid diffusion time constants,
- exchange-current surrogates,
- ohmic resistance,
- plating and aging severity.

## Plating Constraint

The evaluator computes a reduced plating margin:

- negative-electrode OCV contribution,
- kinetic overpotential at the negative electrode,
- electrolyte polarization penalty,
- cold-temperature penalty.

When this margin shrinks:

- plating loss rises,
- plating score worsens,
- sufficiently negative margin triggers invalidation.

This creates the same qualitative decision pressure faced by real fast-charge controllers: a policy may still satisfy voltage and temperature limits while already becoming unsafe from a plating point of view.

## Aging Model

The aging surrogate represents SEI-like side-reaction growth:

- stronger at high temperature,
- stronger at high electrochemical stress,
- coupled to plating-related stress.

It is not intended to be chemistry-accurate. It is intended to create a meaningful optimization cost for "too aggressive but still feasible" charging strategies.

## Configuration Philosophy

All tunable parameters live in:

- `references/battery_config.json`

Users can modify:

- battery capacity and SOC window,
- thermal limits,
- current limits,
- stoichiometry bounds,
- electrochemical time constants,
- kinetic coefficients,
- thermal parameters,
- plating / aging penalty coefficients,
- score weights.

This task is deliberately parameterized so different cells or hypothetical design studies can be represented without editing the evaluator itself.

## Suggested Use

This benchmark is appropriate for:

- evolutionary search,
- agentic code optimization,
- heuristic staged charging design,
- MPC-style policy search over low-dimensional control schedules,
- robustness studies over multiple parameter files.

## References

- [Moura et al. (2017): Battery State Estimation for a Single Particle Model with Electrolyte Dynamics](https://ieeexplore.ieee.org/document/8017015)
- [Bizeray et al. (2016): Reduced-order models of lithium-ion batteries for control applications](https://www.sciencedirect.com/science/article/pii/S0378775316310078)
- [Perez et al. (2017): Optimal charging of Li-ion batteries with coupled electro-thermal-aging dynamics](https://www.sciencedirect.com/)
- [Nature Energy (2019): Challenges and opportunities towards fast-charging battery materials](https://www.nature.com/articles/s41560-019-0405-3)
- [Nature Communications (2023): Extreme fast charging of commercial Li-ion batteries via combined thermal switching and self-heating approaches](https://www.nature.com/articles/s41467-023-38823-9)
