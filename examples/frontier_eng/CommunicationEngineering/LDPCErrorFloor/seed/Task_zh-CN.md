# LDPC 错误地板估计任务

## 背景

低密度奇偶校验（LDPC）码是现代通信系统中广泛使用的强大纠错码。在极低误码率区域（例如 $10^{-6}$ 或更低），LDPC码会出现"错误地板"现象，即误码率曲线趋于平坦而不是继续下降。这是由码的Tanner图中的特殊结构引起的，特别是**Trapping Sets**（陷阱集）- 即使噪声相对较小时也可能导致迭代译码器失败的小子图。

直接蒙特卡洛仿真对于估计错误地板是不切实际的，因为：
1. 错误事件极其罕见（BER $\sim 10^{-6}$ 到 $10^{-12}$）
2. 每次仿真都需要运行迭代译码器，计算成本高
3. 需要数百万或数十亿个样本才能观察到几个错误

**重要性采样**在这里至关重要：我们需要将噪声分布偏向更可能导致trapping set失败的区域，然后使用似然比进行校正。

## 目标

给定：
- 具有奇偶校验矩阵 $H$ 的LDPC码
- 迭代译码器（例如Sum-Product或Min-Sum）
- 噪声方差为 $\sigma^2$ 的AWGN信道
- 目标误码率区域（错误地板，通常为 $10^{-6}$ 到 $10^{-9}$）

使用重要性采样估计错误地板BER，采用针对trapping sets的自定义偏置分布。

## 问题表述

设传输的码字为 $\mathbf{c} \in \{0,1\}^n$（对于线性码，不失一般性可设为全零）。接收信号为：
$$\mathbf{y} = \mathbf{c} + \mathbf{n}$$

其中 $\mathbf{n} \sim \mathcal{N}(0, \sigma^2 \mathbf{I})$ 是AWGN。

译码器产生 $\hat{\mathbf{c}} = \text{Dec}(\mathbf{y})$。如果 $\hat{\mathbf{c}} \neq \mathbf{c}$ 则发生错误。

错误概率为：
$$P_{\text{err}} = \Pr(\hat{\mathbf{c}} \neq \mathbf{c}) = \int_{A_{\text{err}}} f(\mathbf{n}) \, d\mathbf{n}$$

其中 $A_{\text{err}}$ 是错误区域，$f(\mathbf{n})$ 是高斯PDF。

使用重要性采样，我们使用偏置分布 $g(\mathbf{n})$：
$$P_{\text{err}} = \int_{A_{\text{err}}} \frac{f(\mathbf{n})}{g(\mathbf{n})} g(\mathbf{n}) \, d\mathbf{n}$$

挑战在于设计 $g(\mathbf{n})$ 以偏向导致trapping set失败的噪声向量。

## 提交契约

提交一个Python文件，定义：

1. `class TrappingSetSampler(SamplerBase)`
2. `TrappingSetSampler.simulate_variance_controlled(...)`

方法签名：
```python
def simulate_variance_controlled(
    self,
    *,
    code: LDPCCode,
    sigma: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
    fix_tx: bool = True,
    min_errors: int = 10,
):
```

应返回元组或字典，包含：
- `errors_log`: 错误计数的对数
- `weights_log`: 总重要性权重的对数
- `err_ratio`: 误码率估计
- `total_samples`: 使用的总样本数
- `actual_std`: 估计的实际标准差
- `converged`: 指示是否收敛的布尔值

## 评估

评估器将：
1. 使用固定的LDPC码（例如，正则(3,6)码，长度1008）
2. 使用固定迭代次数的Sum-Product译码器（例如50次）
3. 调用您的 `simulate_variance_controlled()` 方法
4. 验证估计的准确性和方差
5. 根据准确性和效率评分

## 评分

- **准确性**：$e = |\log(\hat{P}_{\text{err}} / P_0)|$，其中 $P_0$ 是参考错误地板
- **效率**：运行时间和样本效率
- **最终得分**：$s = t_0 / (t \cdot e + \epsilon)$，其中 $t$ 是中位运行时间

baseline预计运行时间
| 目标耗时 | REPEATS | BATCH_SIZE | MAX_SAMPLES | MIN_ERRORS | TARGET_STD |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 30-45 秒 | 1 | 50 | 50 | 20 | 0.1 |
| 1-2 分钟 | 2 | 50 | 50 | 20 | 0.1 |
| 2-3 分钟 | 2 | 100 | 100 | 20 | 0.1 |
| 5-7 分钟 | 3 | 150 | 150 | 20 | 0.1 |
| 9-14 分钟 | 3 | 300 | 300 | 20 | 0.1 |
| 18-28 分钟 | 3 | 600 | 600 | 20 | 0.1 |
| 45-70 分钟 | 3 | 1500 | 1500 | 20 | 0.1 |

可根据后续需要自行调整参数

冻结评估常量：
- 码：正则(3,6) LDPC，长度1008
- 译码器：Sum-Product，50次迭代
- `sigma = 0.6`（SNR $\approx$ 4.4 dB）
- `target_std = 0.1`
- `max_samples = 50`
- `batch_size = 50`
- `min_errors = 20`
- `repeats = 1`

## 失败情况

如果出现以下情况，得分为 `0`：
- 缺少或无效的 `TrappingSetSampler` 接口
- 无效返回值或非有限指标
- 运行时失败
- 估计准确性太差（$e \geq \epsilon$）

