# 光通信 F2 说明：MCS + 功率联合调度

## 背景

每个用户链路都要同时决定“调制阶数（MCS）”和“发射功率”。

- MCS 越高，理论吞吐越高，但对信道质量要求也越高。
- 功率越高，SNR 通常越好，但会消耗共享预算。

所以这是“吞吐-可靠性-功耗”三者平衡问题。

从 CS 视角，可以理解为 multiple-choice knapsack：

- 每个用户必须从多个 `(MCS, 功率)` 选项中选一个，
- 所有用户共用一个总功率约束，
- 目标函数综合满意度、BER 通过率、频谱效率。

## 你要做什么

只改一个函数：

- 可编辑文件：`baseline/init.py`
- 目标函数：`select_mcs_power(...)`

`verification/` 内评测脚本与 oracle 不改。

## 函数接口

```python
def select_mcs_power(
    user_demands_gbps,
    channel_quality_db,
    total_power_dbm,
    mcs_candidates=(4, 16, 64),
    pmin_dbm=-8.0,
    pmax_dbm=4.0,
    target_ber=1e-3,
    seed=0,
):
    return {
        "mcs": np.ndarray,       # shape (U,), 必须在 mcs_candidates 中
        "power_dbm": np.ndarray, # shape (U,)
    }
```



输入：

- `user_demands_gbps`：每用户吞吐需求。
- `channel_quality_db`：每用户质量估计（SNR-like）。
- `total_power_dbm`：所有用户共享总功率预算。
- `mcs_candidates`：允许选择的调制阶数。
- `pmin_dbm`、`pmax_dbm`：单用户功率上下限。
- `target_ber`：BER 通过阈值。

输出：

- `mcs[u]`：用户 `u` 的调制阶数。
- `power_dbm[u]`：用户 `u` 的发射功率。

## 严格合法性约束

1. 输出必须包含 `mcs` 与 `power_dbm`
2. `mcs.shape == (U,)`
3. `power_dbm.shape == (U,)`
4. `mcs[u]` 必须属于 `mcs_candidates`
5. 功率必须在 `[pmin_dbm, pmax_dbm]`
6. 总线性功率不能超预算

硬约束不通过会直接报错，不进入打分。

## verification 评测流程与指标

固定场景（`seed=123`）：

- 用户数：`22`
- 需求：`[110, 280]` Gbps
- 质量：`[12, 21]` dB
- 总功率：`9 dBm`
- BER 阈值：`7e-4`

每用户评估流程：

1. `snr_db = quality + power`
2. 调用 OptiCommPy `theoryBER` 计算 BER
3. 结合 `log2(M)` 与 BER 可靠性得到吞吐代理

核心指标：

- `demand_satisfaction`
- `ber_pass_ratio`
- `avg_bits_per_symbol`（频谱效率代理）

综合分数：

`0.45*需求满足率 + 0.40*BER通过率 + 0.15*频谱效率项`

metric-level valid 门槛：

- `demand_satisfaction >= 0.40`
- `ber_pass_ratio >= 0.03`

## Baseline（低依赖）

`baseline/init.py` 当前规则：

1. 用简单质量阈值选 MCS（`>=15` 选16，`>=22` 选64），
2. 功率均分，
3. 裁剪到上下限。

仅依赖 `numpy`。

## Oracle（更强参考）

`verification/oracle.py` 更强策略：

- 功率离散化（0.5dB 步长），
- 枚举每用户 `(MCS, 功率)` 组合，
- 在总预算下最大化联合效用。

求解后端：

- `ortools` CP-SAT（离散模型精确求解），
- 无 `ortools` 时回退到确定性 DP。

Oracle 模式：

- `--oracle-mode exact`：优先 CP-SAT
- `--oracle-mode heuristic`：强制 DP
- `--oracle-mode auto`：先 CP-SAT，失败回退 DP

## `verification/outputs/` 文件说明

每次运行生成：

- `summary.json`
- `task2_verification.png`

`summary.json`：

- `candidate`：你的策略评测结果与关键数组
- `oracle`：参考策略结果
- `oracle_meta`：oracle 使用的求解后端信息
- `score_gap_oracle_minus_candidate`：分数差

`task2_verification.png`：

- 左图：信道质量 vs 选择的 MCS（candidate/oracle）
- 右图：每用户实际吞吐柱状对比

可用于排行榜评分与策略诊断。

## 工程意义

该题对应真实自适应链路控制场景：

- 过于激进的 MCS 会导致误码高，
- 过于保守的 MCS 会浪费频谱，
- 功率分配又耦合所有用户。

更优策略意味着同等能耗下更高有效吞吐。
