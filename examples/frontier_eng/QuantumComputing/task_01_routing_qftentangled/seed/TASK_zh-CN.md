# 题目 01：路由导向优化（QFT Entangled）

## 目标
给定 target-independent 输入电路，在 mapped-level 约束下针对 `ibm_falcon_27` 做优化。

本题使用多个 QFT-entangled 测例，降低对单一规模的特化。

## 可修改范围
- 只允许修改 `baseline/solve.py`。

## 评测流程
对每个 case，评测器会：
1. 在 `BenchmarkLevel.INDEP` 生成输入电路。
2. 调用 `optimize_circuit(input_circuit, target, case)`。
3. 对 candidate 做一次 mapped 规范化（`optimization_level=0`）用于公平评分。
4. 直接生成 mapped-level 的 `opt_level=0..3` 参考电路。
5. 输出 candidate 与各 opt-level 对比，并计算归一化分数。

## 输入 / 输出接口
`baseline/solve.py` 必须提供：

```python
def optimize_circuit(input_circuit, target, case):
    ...
    return optimized_circuit
```

输入：
- `input_circuit`：按测例配置生成的 Qiskit `QuantumCircuit`。
- `target`：`ibm_falcon_27` 对应的 Qiskit `Target`。
- `case`：来自 `tests/case_*.json` 的字典。

输出：
- `optimized_circuit`：Qiskit `QuantumCircuit`。

## 成本函数与归一化分数
成本函数：
- `cost = two_qubit_count + 0.2 * depth`

归一化分数：
- `score_0_to_3 = 3 * (opt0_cost - x_cost) / (opt0_cost - opt3_cost)`

含义：
- `opt=0` 参考的分数恒为 `0`。
- `opt=3` 参考的分数恒为 `3`。
- candidate 在同一标尺上打分（可能小于 `0` 或大于 `3`）。

## 测例
- `routing_case_01`（`tests/case_01.json`）：`benchmark=qftentangled`，`num_qubits=9`，`input_opt_level=0`，`target=ibm_falcon_27`
- `routing_case_02`（`tests/case_02.json`）：`benchmark=qftentangled`，`num_qubits=11`，`input_opt_level=1`，`target=ibm_falcon_27`
- `routing_case_03`（`tests/case_03.json`）：`benchmark=qftentangled`，`num_qubits=13`，`input_opt_level=2`，`target=ibm_falcon_27`

## 当前基线（`baseline/solve.py`）
规则重写实现，不直接调用 `transpile`：
1. 去掉 barrier
2. 消去相邻逆门/自反门
3. 合并相邻参数旋转门

## 评测产物保存
每次评测默认保存到 `runs/eval_<timestamp>/`。

每个 case 目录包含：
- `input.qasm` + `input.png`
- `candidate_raw.qasm` + `candidate_raw.png`
- `candidate_canonical.qasm`
- `reference_opt_0.qasm`
- `reference_opt_1.qasm`
- `reference_opt_2.qasm`
- `reference_opt_3.qasm`
