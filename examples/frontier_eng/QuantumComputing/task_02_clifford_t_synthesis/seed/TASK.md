# Task 02: Clifford+T Synthesis Optimization (QFT)

## Goal
Given algorithm-level QFT circuits, synthesize them into `clifford+t` native gates with better quality than a weak baseline.

Multiple sizes are used to reduce overfitting.

## Editable Scope
- Only edit `baseline/solve.py`.

## Evaluation Pipeline
For each case, the evaluator:
1. Builds an input circuit from `BenchmarkLevel.ALG`.
2. Calls `optimize_circuit(input_circuit, target, case)`.
3. Canonicalizes your output to the target gateset (`optimization_level=0`) for fair scoring.
4. Generates direct MQT Bench references at native-gates level with `opt_level=0..3`.
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
- `target`: Qiskit `Target` for `clifford+t`.
- `case`: dict loaded from `tests/case_*.json`.

Output:
- `optimized_circuit`: Qiskit `QuantumCircuit`.

## Cost and Score
Cost function:
- `cost = (T + Tdg) + 0.2 * two_qubit_count + 0.05 * depth`

Normalized score:
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

Interpretation:
- `opt=0` reference has score `0`.
- `opt=3` reference has score `3`.
- Candidate uses the same scale.

## Test Cases
- `clifford_t_case_01` (`tests/case_01.json`): `benchmark=qft`, `num_qubits=3`, `target_gateset=clifford+t`
- `clifford_t_case_02` (`tests/case_02.json`): `benchmark=qft`, `num_qubits=4`, `target_gateset=clifford+t`
- `clifford_t_case_03` (`tests/case_03.json`): `benchmark=qft`, `num_qubits=5`, `target_gateset=clifford+t`

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
