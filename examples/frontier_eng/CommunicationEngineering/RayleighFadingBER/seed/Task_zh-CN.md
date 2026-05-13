# 瑞利衰落信道误码率分析任务

## 背景

在无线通信系统中，多径传播导致信号衰落。瑞利衰落是当没有视距分量时多径传播效应的统计模型。信道增益 $h$ 遵循瑞利分布，使得接收信号功率成为随机变量。

瑞利衰落下的平均误码率涉及计算：
$$P_e = \int_0^{\infty} P_e(\gamma) f_\gamma(\gamma) d\gamma$$

其中 $\gamma = |h|^2 E_s/N_0$ 是瞬时信噪比，$P_e(\gamma)$ 是在信噪比 $\gamma$ 下AWGN的误码率，$f_\gamma(\gamma)$ 是 $\gamma$ 的PDF（对于瑞利衰落为指数分布）。

在极低的目标误码率（例如 $10^{-6}$ 或更低）下，大多数错误发生在**深衰落**事件中，此时 $\gamma$ 非常小。直接蒙特卡洛仿真需要许多样本才能观察到这些罕见事件。

**重要性采样**可以将信道增益分布偏向深衰落区域，显著提高仿真效率。

## 目标

给定：
- 具有 $L$ 个分集支路的瑞利衰落信道（例如，多个天线）
- 分集合并方案：最大比合并（MRC）或选择合并（SC）
- 调制：BPSK或QPSK
- 目标误码率区域：$10^{-6}$ 到 $10^{-9}$

使用重要性采样估计平均误码率，采用针对深衰落事件的偏置分布。

## 问题表述

对于 $L$ 个独立的瑞利衰落支路，信道增益为：
$$h_i \sim \mathcal{CN}(0, \sigma_h^2), \quad i=1,\ldots,L$$

幅度 $|h_i|$ 遵循尺度参数为 $\sigma_h$ 的瑞利分布。

对于**最大比合并（MRC）**：
- 合并信噪比：$\gamma_{\text{MRC}} = \sum_{i=1}^L |h_i|^2 E_s/N_0$
- 合并信号具有 $2L$ 自由度的卡方分布

对于**选择合并（SC）**：
- 合并信噪比：$\gamma_{\text{SC}} = \max_i |h_i|^2 E_s/N_0$

在瞬时信噪比 $\gamma$ 下BPSK的误码率为：
$$P_e(\gamma) = Q(\sqrt{2\gamma})$$

其中 $Q(x)$ 是Q函数。

平均误码率为：
$$P_e = \mathbb{E}[P_e(\gamma)] = \int P_e(\gamma) f_\gamma(\gamma) d\gamma$$

使用重要性采样，我们将信道增益分布 $f_h(\mathbf{h})$ 偏置为 $g_h(\mathbf{h})$：
$$P_e = \int P_e(\gamma(\mathbf{h})) \frac{f_h(\mathbf{h})}{g_h(\mathbf{h})} g_h(\mathbf{h}) d\mathbf{h}$$

## 提交契约

提交一个Python文件，定义：

1. `class DeepFadeSampler(SamplerBase)`
2. `DeepFadeSampler.simulate_variance_controlled(...)`

方法签名：
```python
def simulate_variance_controlled(
    self,
    *,
    channel_model,
    diversity_type: str,  # "MRC" or "SC"
    modulation: str,  # "BPSK" or "QPSK"
    snr_db: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
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
1. 使用固定的信道参数（例如，$L=4$ 个分集支路）
2. 使用固定的分集方案（MRC或SC）
3. 调用您的 `simulate_variance_controlled()` 方法
4. 验证估计的准确性和方差
5. 根据准确性和效率评分

## 评分

- **准确性**：$e = |\log(\hat{P}_e / P_0)|$，其中 $P_0$ 是参考误码率
- **效率**：运行时间和样本效率
- **最终得分**：$s = t_0 / (t \cdot e + \epsilon)$，其中 $t$ 是中位运行时间

冻结评估常量：
- 分集支路：$L = 4$
- 分集类型：MRC
- 调制：BPSK
- 平均信噪比：10 dB
- `target_std = 0.1`
- `max_samples = 50000`
- `batch_size = 5000`
- `min_errors = 20`
- `repeats = 3`

## 失败情况

如果出现以下情况，得分为 `0`：
- 缺少或无效的 `DeepFadeSampler` 接口
- 无效返回值或非有限指标
- 运行时失败
- 估计准确性太差（$e \geq \epsilon$）

