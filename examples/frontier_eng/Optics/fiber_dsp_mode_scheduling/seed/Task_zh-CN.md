# 光通信 F3 说明：DSP 模式调度（EDC vs DBP）

## 背景

相干光接收机里常见两种 DSP 处理模式：

- `EDC`：延迟低、计算开销小，但补偿能力较弱。
- `DBP`：补偿更强、链路质量更好，但延迟和计算开销更大。

因此每个用户是否启用 DBP，是典型的“质量收益 vs 时延成本”取舍。

从 CS 视角，这是一个二元决策优化：

- 每用户选择 `0/1` 模式，
- 最大化整体加权效用，
- 同时满足全局时延预算（可选 DBP 用户数量上限）。

## 你要做什么

只改一个函数：

- 可编辑文件：`baseline/init.py`
- 目标函数：`choose_dsp_mode(...)`

`verification/` 下脚本和 oracle 保持只读。

## 函数接口

```python
def choose_dsp_mode(user_features, latency_budget_s, max_dbp_users=None, seed=0):
    return {"mode": np.ndarray}  # shape (U,), 元素在 {0,1}
```

模式约定：

- `0` = EDC
- `1` = DBP



`user_features` 是按用户对齐的数组字典：

- `est_snr_db`：未启用 DBP 前的 SNR 估计
- `traffic_weight`：用户业务权重（重要性）
- `dbp_gain_db`：启用 DBP 时预期 SNR 增益
- `edc_latency_s`：选择 EDC 时延
- `dbp_latency_s`：选择 DBP 时延
- `modulation_order`：BER 模型参数
- `target_ber`：BER 通过阈值

其他输入：

- `latency_budget_s`：全局时延预算
- `max_dbp_users`：可选的 DBP 用户上限

输出：

- `mode[u]`：用户 `u` 的模式选择（0/1）。

## 严格合法性约束

1. 输出必须包含 `mode`
2. `mode.shape == (U,)`
3. 每个值只能是 `0` 或 `1`

随后还要满足 metric-level valid：

- 总时延不超预算容差
- BER 通过率不低于门槛

## verification 评测流程与指标

固定场景（`seed=7`）是“结构化困难样本”：

- A 组：SNR 很低、权重低、DBP 成本高
- B 组：SNR 中等、权重很高、DBP 增益高且成本低
- C 组：SNR 很高、DBP 边际收益低

规模：

- 用户数：`24`
- `max_dbp_users = 7`

评估逻辑：

1. 有效 SNR = `est_snr_db + mode * dbp_gain_db`
2. 用 OptiCommPy `theoryBER` 算 BER
3. BER 转换为可靠性后，与 `traffic_weight` 结合得到效用
4. 根据模式汇总总时延

指标：

- `weighted_utility`
- `ber_pass_ratio`
- `dbp_ratio`
- `latency_overflow`

综合分数：

`0.65*加权效用 + 0.30*BER通过率 + 0.05*(1-DBP占比) - 0.70*超预算惩罚`

valid 门槛：

- `latency <= budget * 1.001`
- `ber_pass_ratio >= 0.18`

## Baseline（低依赖）

`baseline/init.py` 当前逻辑：

1. 先按 SNR 从低到高排序；
2. 依次给低 SNR 用户分配 DBP；
3. 一旦预算（或 DBP 数量上限）触发就停止。

简单易懂，但没有全局最优意识。

## Oracle（更强参考）

`verification/oracle.py` 把问题建模为背包风格优化：

- 每用户“DBP 相比 EDC 的效用增益”作为价值，
- 额外时延作为成本，
- 有 `ortools` 时用 CP-SAT，
- 无 `ortools` 时用确定性 DP，
- 最后做严格时延清理避免超预算。

Oracle 模式：

- `--oracle-mode exact`：优先 CP-SAT
- `--oracle-mode heuristic`：强制 DP
- `--oracle-mode auto`：先 CP-SAT，失败回退 DP

## `verification/outputs/` 文件说明

每次运行会输出：

- `summary.json`
- `task3_verification.png`

`summary.json`：

- `candidate`：你的策略评测结果
- `oracle`：参考策略评测结果
- `oracle_meta`：oracle 实际求解后端
- `score_gap_oracle_minus_candidate`：分差

`task3_verification.png`：

- 左图：用户 SNR 分布上标记 candidate/oracle 选择 DBP 的用户
- 右图：candidate/oracle 总时延柱状图 + 预算线

可用于判断 DBP 是否分给了“高收益用户”。

## 工程意义

这题对应真实接收机资源调度：

- 强 DSP 可提升质量，
- 但延迟与计算开销会限制系统实时性，
- 调度策略需要优先照顾高价值流量。

因此它是典型的工程化“质量-时延”联合优化问题。
