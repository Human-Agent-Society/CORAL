# 光通信 F4 说明：带保护带约束的频谱打包

## 背景

弹性光网络可抽象为：把不同宽度的业务请求，打包到一维有限频谱槽位中。

每个用户请求一段连续槽位，且必须满足：

- 分配区间不能重叠，
- 区间之间要留保护带，
- 总槽位数量有限。

这和带额外约束的 bin packing / interval scheduling 很接近。

## 你要做什么

只改一个函数：

- 可编辑文件：`baseline/init.py`
- 目标函数：`pack_spectrum(...)`

`verification/` 下评测与 oracle 为只读参考。

## 函数接口

```python
def pack_spectrum(user_demand_slots, n_slots, guard_slots=1, seed=0):
    return {"alloc": np.ndarray}  # shape (U, 2)
```

`alloc[i]` 编码：

- 分配成功：`(start, width)`
- 未分配：`(-1, 0)`



输入：

- `user_demand_slots`：每用户请求的连续槽位宽度。
- `n_slots`：总可用槽位数。
- `guard_slots`：相邻业务之间必须保留的保护带。

输出：

- `alloc[i] = (start, width)`：用户 `i` 被接纳并放置。
- `alloc[i] = (-1, 0)`：用户 `i` 被拒绝。

## 严格合法性约束

`verification` 会严格检查几何合法性：

1. `alloc.shape == (U, 2)`
2. 对已分配用户：`start >= 0`、`width > 0`、`start + width <= n_slots`
3. `width` 必须等于该用户请求宽度
4. 任意两业务不能重叠
5. 任意两业务之间满足保护带约束

几何不合法时，即使其它指标高，也会判 invalid。

## verification 评测流程与指标

固定场景（`seed=99`）是“难打包”分布：

- 请求宽度双峰分布：大量小请求 + 少量大请求
- 总槽位：`68`
- 保护带：`1`

评测除了几何指标，还引入 BER 代理：

- 每用户有基础 SNR，
- 频谱上相邻业务会造成邻道干扰，
- 有效 SNR 经 OptiCommPy `theoryBER` 转为 BER。

指标：

- `acceptance_ratio`（接纳率）
- `utilization`（利用率）
- `compactness`（紧凑性，空闲块越少越高）
- `ber_pass_ratio`

综合分数：

`0.80*接纳率 + 0.05*利用率 + 0.05*紧凑性 + 0.10*BER通过率`

valid 门槛：

- `acceptance_ratio >= 0.25`
- `ber_pass_ratio >= 0.80`
- 几何合法

## Baseline（低依赖）

`baseline/init.py` 当前用 First-Fit Decreasing：

1. 按请求宽度从大到小排序，
2. 为每个请求找第一个可行位置，
3. 找不到就拒绝。

实现简单确定，但容易产生碎片，影响后续接纳率。

## Oracle（更强参考）

`verification/oracle.py` 提供多种更强后端：

- `heuristic`：小请求优先 + best-fit（考虑碎片）
- `hybrid`：在用户顺序上做局部搜索，再 best-fit 放置
- `exact_geometry`：OR-Tools CP-SAT 对几何目标做精确求解
- `auto`：比较可用后端代理分，自动选更优

重要说明：

- 最终打分包含 BER 代理项，
- `exact_geometry` 仅对几何子目标精确，不保证最终总分最优，
- 实测里 `hybrid` 常常在总分上更强。

## `verification/outputs/` 文件说明

每次运行会生成：

- `summary.json`
- `task4_verification.png`

`summary.json`：

- `candidate`：你策略的指标与分配结果
- `oracle`：参考策略指标与分配结果
- `oracle_meta`：oracle 实际使用的后端
- `score_gap_oracle_minus_candidate`：分差

`task4_verification.png`：

- 上图：candidate 的频谱占用可视化
- 下图：oracle 的频谱占用可视化

这张图很适合快速定位碎片化和接纳率问题。

## 工程意义

这个任务的目标和实际资源经济性高度一致：

- 优先提高接纳率（核心业务 KPI），
- 兼顾频谱利用与碎片控制，
- 避免因干扰导致质量退化过多。

本质上是网络资源编排中的“可服务规模 vs 质量风险”平衡问题。
