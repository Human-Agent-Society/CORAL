# PMD Simulation

Navigation document for this task.

## Goal

Simulate Polarization Mode Dispersion (PMD) in optical fiber systems using importance sampling. Optical fiber systems require extremely low outage probabilities (e.g., $10^{-12}$), and PMD is a random physical phenomenon. This is considered one of the most successful applications of importance sampling in engineering.

## Files

- `Task.md`: task contract and scoring rules (English).
- `Task_zh-CN.md`: Chinese version of task contract.
- `scripts/init.py`: minimal runnable starter.
- `baseline/solution.py`: baseline implementation.
- `runtime/`: task runtime components (PMD model, fiber simulation).
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: minimal dependencies for local evaluator run.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/PMDSimulation/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/CommunicationEngineering/PMDSimulation/verification/evaluator.py benchmarks/CommunicationEngineering/PMDSimulation/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/CommunicationEngineering/PMDSimulation && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` is expected to be runnable and should produce non-zero `outage_prob_log` and `valid=1.0` under a normal environment.

## frontier_eval Task Name

This task uses the unified task framework. Run with:

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/PMDSimulation algorithm.iterations=0
```


