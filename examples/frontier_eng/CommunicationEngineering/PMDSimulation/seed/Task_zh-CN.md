# PMD 仿真任务

## 背景

极化模色散（PMD）是高速光纤通信系统中的关键损伤。PMD导致脉冲展宽和符号间干扰，限制了可实现的数据速率和传输距离。

PMD源于光纤中的随机双折射，其中两个正交的偏振模式以略微不同的速度传播。PMD向量 $\vec{\tau}$ 沿着光纤根据随机游走模型演化，使其成为随机过程。

**停机概率**定义为差分群延迟（DGD）超过阈值的概率：
$$P_{\text{out}} = \Pr(|\vec{\tau}| > \tau_{\text{th}})$$

对于要求停机概率为 $10^{-12}$ 或更低的现代系统，直接蒙特卡洛仿真完全不切实际 - 需要数万亿个样本。

**重要性采样**在这里至关重要。关键洞察是将PMD演化偏向DGD较大的区域，然后使用似然比进行校正。这是重要性采样在工程实践中最成功的应用之一。

## 目标

给定：
- 光纤长度 $L$
- PMD系数 $D_p$（典型单位：ps/√km）
- DGD阈值 $\tau_{\text{th}}$
- 目标停机概率区域：$10^{-10}$ 到 $10^{-12}$

使用重要性采样估计停机概率，采用针对高DGD事件的偏置分布。

## 问题表述

PMD向量 $\vec{\tau}(z)$ 沿着光纤演化：
$$\frac{d\vec{\tau}}{dz} = \vec{\beta}(z) + \vec{\Omega}(z) \times \vec{\tau}(z)$$

其中：
- $\vec{\beta}(z)$ 是局部双折射向量
- $\vec{\Omega}(z)$ 是旋转向量
- 两者都是随机过程

对于仿真，我们将光纤离散化为段。在距离 $L$ 处的DGD为：
$$\tau(L) = |\vec{\tau}(L)|$$

停机概率为：
$$P_{\text{out}} = \Pr(\tau(L) > \tau_{\text{th}}) = \int_{\tau(L) > \tau_{\text{th}}} f(\vec{\tau}) d\vec{\tau}$$

其中 $f(\vec{\tau})$ 是PMD向量分量的联合PDF。

使用重要性采样，我们偏置PMD演化：
$$P_{\text{out}} = \int_{\tau(L) > \tau_{\text{th}}} \frac{f(\vec{\tau})}{g(\vec{\tau})} g(\vec{\tau}) d\vec{\tau}$$

## 提交契约

提交一个Python文件，定义：

1. `class PMDSampler(SamplerBase)`
2. `PMDSampler.simulate_variance_controlled(...)`

方法签名：
```python
def simulate_variance_controlled(
    self,
    *,
    fiber_model,
    dgd_threshold: float,
    target_std: float,
    max_samples: int,
    batch_size: int,
    min_outages: int = 10,
):
```

应返回元组或字典，包含：
- `outages_log`: 停机计数的对数
- `weights_log`: 总重要性权重的对数
- `outage_prob`: 停机概率估计
- `total_samples`: 使用的总样本数
- `actual_std`: 估计的实际标准差
- `converged`: 指示是否收敛的布尔值

## 评估

评估器将：
1. 使用固定的光纤参数（长度、PMD系数）
2. 使用固定的DGD阈值
3. 调用您的 `simulate_variance_controlled()` 方法
4. 验证估计的准确性和方差
5. 根据准确性和效率评分

## 评分

- **准确性**：$e = |\log(\hat{P}_{\text{out}} / P_0)|$，其中 $P_0$ 是参考停机概率
- **效率**：运行时间和样本效率
- **最终得分**：$s = t_0 / (t \cdot e + \epsilon)$，其中 $t$ 是中位运行时间

冻结评估常量：
- 光纤长度：$L = 100$ km
- PMD系数：$D_p = 0.5$ ps/√km
- DGD阈值：$\tau_{\text{th}} = 30$ ps
- `target_std = 0.1`
- `max_samples = 50000`
- `batch_size = 5000`
- `min_outages = 20`
- `repeats = 3`

## 失败情况

如果出现以下情况，得分为 `0`：
- 缺少或无效的 `PMDSampler` 接口
- 无效返回值或非有限指标
- 运行时失败
- 估计准确性太差（$e \geq \epsilon$）

