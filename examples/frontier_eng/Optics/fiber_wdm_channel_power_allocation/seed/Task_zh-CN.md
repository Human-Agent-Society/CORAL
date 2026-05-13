# 光通信 F1 说明：WDM 信道与功率分配

## 背景

WDM（波分复用）系统里，多名用户共享同一根光纤，通过不同“波长信道”并行传输。

你需要同时决定两件事：

- 每个用户使用哪个信道（离散决策），
- 每个信道发多少功率（连续资源分配）。

功率高通常能提升信号质量，但相邻信道会产生串扰；同时总功率受预算限制。

从 CS 视角，这题是“分配 + 连续优化 + 约束检查”的组合问题。

## 你要做什么

只改一个核心函数：

- 可编辑文件：`baseline/init.py`
- 目标函数：`allocate_wdm(...)`

`verification/` 下的评测逻辑视为只读基准。

## 函数接口

```python
def allocate_wdm(
    user_demands_gbps,
    channel_centers_hz,
    total_power_dbm,
    pmin_dbm=-8.0,
    pmax_dbm=3.0,
    target_ber=1e-3,
    seed=0,
):
    return {
        "assignment": np.ndarray,  # shape (U,), int, 信道索引或-1
        "power_dbm": np.ndarray,   # shape (C,), float, 每信道功率
    }
```



输入：

- `user_demands_gbps`：`U` 个用户的带宽需求。
- `channel_centers_hz`：`C` 个可用信道中心频率。
- `total_power_dbm`：总功率预算。注意评测会在线性功率域（mW）检查，而不是直接做 dBm 相加。
- `pmin_dbm`、`pmax_dbm`：每信道功率上下限。
- `target_ber`：BER 通过阈值。

输出：

- `assignment[u]`：
  - `-1` 表示用户 `u` 不服务，
  - `0..C-1` 表示分配到对应信道。
- `power_dbm[ch]`：信道 `ch` 的发射功率。

## 严格合法性约束（hard valid）

必须同时满足：

1. `assignment.shape == (U,)`
2. `power_dbm.shape == (C,)`
3. `assignment` 取值在 `[-1, C-1]`
4. 一个信道不能分给多个用户
5. 所有信道功率在 `[pmin_dbm, pmax_dbm]`
6. 总线性功率 `sum(10^(p_dbm/10)) <= 10^(total_power_dbm/10)`

如果结构不合法，评测会直接报错退出。

## verification 评测流程与指标

`verification/run_validation.py` 用固定场景（`seed=42`）同时评估 candidate 和 oracle。

场景规模：

- 用户数：`14`
- 信道数：`20`
- 需求：`[180, 320]` Gbps 均匀采样

评估逻辑（工程代理模型）：

1. 计算每个已服务用户的信号功率与串扰功率。
2. 得到 `SNR`。
3. 用 OptiCommPy 的 `theoryBER`（QAM）计算 BER。
4. 用 SNR 映射吞吐代理容量。

核心指标：

- `demand_satisfaction`
- `ber_pass_ratio`
- `spectral_utilization`
- `avg_snr_db`

综合分数：

`0.35*需求满足 + 0.40*BER通过率 + 0.05*频谱利用率 + 0.20*SNR项 - 0.15*功率惩罚`

metric-level valid 门槛：

- `demand_satisfaction >= 0.30`
- `ber_pass_ratio >= 0.20`
- `spectral_utilization >= 0.55`

## Baseline（低依赖）

`baseline/init.py` 当前策略：

1. 用户按索引顺序占用信道；
2. 活跃信道等功率分配；
3. 再裁剪到功率上下限。

只依赖 `numpy`，刻意保持简单。

## Oracle（更强参考）

`verification/oracle.py` 用更强的组合策略：

- 串扰感知的初始分配（尽量拉开信道）
- 需求感知的用户-信道映射
- 需求加权的功率初始化
- assignment + power 的局部搜索
- 可选 SciPy 差分进化做功率细化

Oracle 模式：

- `--oracle-mode heuristic`：仅启发式/局部搜索
- `--oracle-mode hybrid_scipy`：启发式 + SciPy 全局细化
- `--oracle-mode auto`：自动选择可用更强后端

## `verification/outputs/` 里文件的作用

每次运行会生成两个核心文件：

- `summary.json`
- `task1_verification.png`

`summary.json` 用于打分与复现实验，包含：

- `candidate`：你当前策略的完整评测结果
- `oracle`：参考策略评测结果
- `oracle_meta`：oracle 使用了什么后端/模式
- `score_gap_oracle_minus_candidate`：参考分 - candidate 分

`task1_verification.png` 用于诊断策略行为：

- 左图：每用户“需求 vs 实际容量”（candidate 与 oracle 对比）
- 右图：每信道功率曲线（candidate 与 oracle 对比）

## 工程意义

这题反映真实网络控制中的核心冲突：

- 多服务用户 vs 低误码可靠性，
- 更高功率 vs 更强串扰，
- 静态规则 vs 自适应优化。

策略更优通常意味着更高吞吐/功率效率和更低链路风险。
