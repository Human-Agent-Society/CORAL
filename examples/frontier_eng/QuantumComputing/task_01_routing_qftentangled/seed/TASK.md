# Task 01: Routing-Oriented Optimization (QFT Entangled)

## Goal
Given target-independent input circuits, optimize them for `ibm_falcon_27` under mapped-level constraints.

This task uses multiple QFT-entangled cases to reduce single-case overfitting.

## Editable Scope
- Only edit `baseline/solve.py`.

## Evaluation Pipeline
For each case, the evaluator:
1. Builds an input circuit from MQT Bench at `BenchmarkLevel.INDEP`.
2. Calls `optimize_circuit(input_circuit, target, case)`.
3. Canonicalizes your output once via mapped transpilation (`optimization_level=0`) for fair scoring.
4. Generates direct MQT Bench references at mapped-level `opt_level=0..3`.
5. Reports candidate vs references and computes normalized score.

## Input / Output Interface
`baseline/solve.py` must provide:

```python
def optimize_circuit(input_circuit, target, case):
    ...
    return optimized_circuit
```

Input:
- `input_circuit`: Qiskit `QuantumCircuit` generated from case config.
- `target`: Qiskit `Target` for `ibm_falcon_27`.
- `case`: dict loaded from `tests/case_*.json`.

Output:
- `optimized_circuit`: Qiskit `QuantumCircuit`.

## Cost and Score
Cost function:
- `cost = two_qubit_count + 0.2 * depth`

Normalized score:
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

Interpretation:
- `opt=0` reference always has score `0`.
- `opt=3` reference always has score `3`.
- Candidate score is measured on the same scale (it may be below `0` or above `3` if candidate is worse/better than those anchors).

## Test Cases
- `routing_case_01` (`tests/case_01.json`): `benchmark=qftentangled`, `num_qubits=9`, `input_opt_level=0`, `target=ibm_falcon_27`
- `routing_case_02` (`tests/case_02.json`): `benchmark=qftentangled`, `num_qubits=11`, `input_opt_level=1`, `target=ibm_falcon_27`
- `routing_case_03` (`tests/case_03.json`): `benchmark=qftentangled`, `num_qubits=13`, `input_opt_level=2`, `target=ibm_falcon_27`

## Current Baseline (`baseline/solve.py`)
Rule-based structural rewrites without directly calling `transpile`:
1. barrier removal
2. adjacent inverse/self-inverse cancellation
3. adjacent parameterized-rotation merge

## Saved Artifacts
Each run saves to `runs/eval_<timestamp>/`.

Per case artifacts include:
- `input.qasm` + `input.png`
- `candidate_raw.qasm` + `candidate_raw.png`
- `candidate_canonical.qasm`
- `reference_opt_0.qasm`
- `reference_opt_1.qasm`
- `reference_opt_2.qasm`
- `reference_opt_3.qasm`
