# LDPC Error Floor Estimation

Navigation document for this task.

## Goal

Estimate the error floor for LDPC (Low-Density Parity-Check) codes using importance sampling. LDPC codes exhibit an "error floor" phenomenon at very low BER regions, caused by special structures in the code graph (e.g., Trapping Sets). Direct Monte Carlo simulation is nearly impossible to observe these rare events.

## Files

- `Task.md`: task contract and scoring rules (English).
- `Task_zh-CN.md`: Chinese version of task contract.
- `scripts/init.py`: minimal runnable starter.
- `baseline/solution.py`: baseline implementation.
- `runtime/`: task runtime components (LDPC code, decoder, sampler base class).
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: minimal dependencies for local evaluator run.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/CommunicationEngineering/LDPCErrorFloor/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/CommunicationEngineering/LDPCErrorFloor/verification/evaluator.py benchmarks/CommunicationEngineering/LDPCErrorFloor/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/CommunicationEngineering/LDPCErrorFloor && python verification/evaluator.py scripts/init.py
```

`scripts/init.py` is expected to be runnable and should produce non-zero `error_rate_log` and `valid=1.0` under a normal environment.

## frontier_eval Task Name

This task takes a long time to run, and the upper limit of the running time is increased

This task uses the unified task framework. Run with:

```bash
python -m frontier_eval task=unified task.benchmark=CommunicationEngineering/LDPCErrorFloor algorithm.iterations=0 algorithm.oe.evaluator.timeout=60
```
