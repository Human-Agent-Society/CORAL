# Particle Physics: Muon Tomography Detector Placement Optimization

English | [简体中文](./README_zh-CN.md)

## 1. Task Overview

This task (Muon Tomography Optimization) is a core optimization problem in the **Particle Physics and Nuclear Engineering** domain within the `Frontier-Eng` benchmark.

Muon tomography utilizes the transmission attenuation characteristics of cosmic ray muons to probe the internal structure of large objects (e.g., pyramids, volcanoes, nuclear reactors). This task challenges the AI Agent to find an optimal spatial layout for a detector array, considering real physical constraints (such as the $\cos^2(\theta_z)$ attenuation of muon flux with the zenith angle) and strict economic constraints (detector manufacturing costs and underground excavation costs).

> **Core Challenge**: The Agent cannot simply stack detectors as close to the target as possible. Instead, it must perform precise spatial geometric calculations to find the optimal Pareto solution between "maximizing effective signal reception" and "minimizing engineering costs."

For detailed physical and mathematical models, objective functions, and I/O formats designed for the Agent, please refer to the core task document: [Task.md](./Task.md).

## 2. Local Run

After preparing the `frontier-eval-driver` environment, you can run the benchmark directly from the task directory:

```bash
cd benchmarks/ParticlePhysics/MuonTomography
../../../.venvs/frontier-eval-driver/bin/python baseline/solution.py
../../../.venvs/frontier-eval-driver/bin/python verification/evaluator.py solution.json
```

`verification/requirements.txt` currently only requires `numpy>=1.24.0`.

The baseline above has been verified in this repository with the following result:

```json
{"score": 199.32012533144325, "status": "success", "metrics": {"total_signal": 309.32012533144325, "total_cost": 110.0, "valid_detectors": 4}}
```

## 3. Run with `frontier_eval`

This task now runs through the unified benchmark entry:
`task=unified task.benchmark=ParticlePhysics/MuonTomography`.

From the repository root, the standard compatibility check is:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=ParticlePhysics/MuonTomography algorithm=openevolve algorithm.iterations=0
```

After completing the framework-level `.env` or model configuration described in [frontier_eval/README.md](../../../frontier_eval/README.md), you can start a real search by increasing `algorithm.iterations`, for example:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=ParticlePhysics/MuonTomography algorithm=openevolve algorithm.iterations=10
```

The old alias `task=muon_tomography` is still supported and routes to the same unified benchmark via config.
