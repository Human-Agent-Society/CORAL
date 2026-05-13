# Rayleigh Fading BER Analysis

Navigation document for this task.

## Goal

Analyze Bit Error Rate (BER) under Rayleigh fading channels using importance sampling. In multipath fading channels, channel gain $h$ is a random variable, making average BER calculation involve complex integration. Importance sampling is used to simulate deep fade events efficiently.

## Files

- `Task.md`: task contract and scoring rules (English).
- `Task_zh-CN.md`: Chinese version of task contract.
- `scripts/init.py`: minimal runnable starter.
- `baseline/solution.py`: baseline implementation.
- `runtime/`: task runtime components (channel models, diversity combiners).
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: minimal dependencies for local evaluator run.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/RayleighFadingBER/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/CommunicationEngineering/RayleighFadingBER/verification/evaluator.py benchmarks/CommunicationEngineering/RayleighFadingBER/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/CommunicationEngineering/RayleighFadingBER && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` is expected to be runnable and should produce non-zero `error_rate_log` and `valid=1.0` under a normal environment.

## frontier_eval Task Name

This task uses the unified task framework. Run with:

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER algorithm.iterations=0
```

Or use the short alias (if registered):

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/RayleighFadingBER algorithm.iterations=0
```


