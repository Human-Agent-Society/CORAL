# HighReliableSimulation 任务说明

## 目标

在稀有错误场景下，估计 AWGN 信道中 Hamming(127,120) 的 BER。
你需要实现 `MySampler`，并支持方差受控仿真。

## 提交协议

提交一个 Python 文件，需定义：

1. `class MySampler(SamplerBase)`
2. `MySampler.simulate_variance_controlled(...)`，用于本地兼容运行

官方评分使用 benchmark 自己持有的 canonical 仿真循环：

```python
sampler = MySampler(code=code, seed=seed)
result = code.simulate_variance_controlled(
    noise_std=DEV_SIGMA,
    target_std=TARGET_STD,
    max_samples=MAX_SAMPLES,
    sampler=sampler,
    batch_size=BATCH_SIZE,
    fix_tx=True,
    min_errors=MIN_ERRORS,
)
```

其中 `code` 由评测器固定为 `HammingCode(r=7, decoder="binary")`，并设置 `ChaseDecoder(t=3)`。
这样可以避免候选程序通过自报聚合统计量进行 reward hacking。

## 返回格式

`MySampler.simulate_variance_controlled(...)` 仍可返回以下两类：

- 至少包含 6 项的 tuple/list：
  `(errors_log, weights_log, err_ratio, total_samples, actual_std, converged)`
- 具有等价字段的 dict。

但官方评分不会信任这些自报结果，而是通过上面的 canonical benchmark loop 重新计算。

## 冻结评测常量

- `sigma = 0.268`
- `target_std = 0.05`
- `max_samples = 100000`
- `batch_size = 10000`
- `min_errors = 20`
- `r0 = 7.261287772505011e-07`
- `t0 = 10.4001037335396`
- `epsilon = 0.8`
- `repeats = 3`

## 评分规则

- `e = |log(r / r0)|`，其中 `r = exp(err_rate_log)`。
- 设 `s` 为多次重复中 `actual_std` 的中位数。
- 若 `e >= epsilon` 或 `s > target_std`，则本次评测无效，得分为 `-1e18`。
- 否则：`score = t0 / (t * e + 1e-6)`，其中 `t` 为运行时间中位数。

## 失败条件

以下任一情况得分为 `-1e18`：

- `MySampler` 接口缺失或不合法
- canonical benchmark loop 产生非法或非有限指标
- 运行失败
- `actual_std` 中位数未达到 `target_std`
