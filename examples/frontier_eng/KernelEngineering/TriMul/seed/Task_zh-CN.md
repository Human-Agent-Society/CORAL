# 描述

您将实现三角形乘法更新 (TriMul) 模块，该模块是 BioML 中 AlphaFold3、Chai、Protenix 和其他蛋白质结构预测模型的核心操作。

TriMul 算子作用于形状为 [B, N, N, C] 的 4D 张量。

你的任务：

- 实现 [AlphaFold3](references/Accurate%20structure%20prediction%20of%20biomolecular%20interactions%20with%20AlphaFold%203.pdf) 论文中 TriMul 运算符的“输出”版本。
- 在这个版本中，你不需要计算或存储梯度。你只需要实现前向传播即可。

输入：

- data：元组（输入：torch.Tensor，权重：Dict[str，torch.Tensor]，配置：Dict）
    - 输入：形状为 [bs, seq_len, seq_len, dim] 的输入张量
    - mask：形状为 [bs, seq_len, seq_len] 的掩码张量
    - 权重：包含模型权重的字典
    - config：包含模型配置参数的字典

输出：

- 包含以下内容的元组：
    - 输出：处理后的张量 [bs, seq_len, seq_len, dim]

以下是更为详细的描述

### **引言与动机**

*“对于内核（Kernel）开发者来说，这是一个非常非常有趣且具有影响力的难题。祝好运 :p” —— az* 在这些 GPU MODE 内核编写竞赛中，你会看到许多内核/问题都围绕着大型语言模型训练——例如，我们上一届的竞赛就集中在 DeepSeek-V3/R1 中使用的流行单设备内核上。未来的许多问题可能也会围绕通信内核展开，比如我们会提供一个完整的节点，例如专家并行（expert parallelism）MoE。

我们脑海中的许多这类内核已经被来自 DeepSeek、OpenAI、Anthropic、Google DeepMind 等实验室的专家们进行了深度优化，因此我们想设计一些仍然有趣，且一旦解决就能有实际用例的难题。我们立刻想到的第一个问题就是 AlphaFold2 和 AlphaFold3 中使用的**三角形乘法更新 (Triangle Multiplicative Update)**，这是 BioML（生物机器学习）领域中一系列极具影响力的工作，并让 **[John Jumper 和 Demis Hassabis 赢得了 2024 年诺贝尔化学奖](https://www.nobelprize.org/prizes/chemistry/2024/press-release/)**。由于其三次方的  运算量，这个算子特别难搞。该算子的峰值内存占用非常糟糕，以至于 AlphaFold3 的大多数实现版本（参见 **[Ligo 的开源复现](https://github.com/Ligo-Biosciences/AlphaFold3)** 和 MIT 的 **[Boltz-2](https://github.com/jwohlwend/boltz)**）在训练期间都将 batch size 保持为 1，尽管这些模型的参数量还不到 10 亿！

***编辑：**有趣的是，在撰写这个题目时，我们注意到 NVIDIA 实际上已经发布了他们在 cuEquivariance 库中开发这个内核的消息——真是太巧了！我们要求参赛者在解决方案中不要使用这个库，因为它是闭源的（我们将在排行榜上自动和手动移除这些解决方案）。说实话，我相信你们所有人都能轻松击败他们的解决方案！*

动机已经说得够多了，现在是时候**开始编码**了！

---

**问题陈述：外向三角形乘法 (Outgoing TriMul) 内核**

在这个问题中，你需要处理成对的嵌入序列 (pairwise sequence of embeddings)，这比语言模型中使用的嵌入序列更棘手。你的张量将具有一个（很小的）批次大小 (batch size)、两个（大小相等的）序列维度，以及一个隐藏维度。以下是取自 AlphaFold3 补充材料的 batch size=1 时的直观图解：

基本上，你的输入张量将被分成两条路径（通过相同的变换，只是权重不同）。这两条路径会经过非常简单的变换（一个 LayerNorm、一个 sigmoid 以及一些线性变换），直到最后使用“三角形乘法”算子将它们组合起来，这基本上只是一个批次的矩阵乘法，其中批次维度实际上是序列维度（参见下方代码）。

**备注：** 算子本身看起来相当简单，但你会注意到这个算法中有很多非常棘手的部分。也就是说，使用 tensor cores / matrix cores 绝非易事，因为你需要让所有数据沿着特定维度连续 (contiguous)。提供给你的张量是 `LayoutRight` 步幅的，即沿着通道 (channel) 维度是连续的。

### **形式化规范：**

给定一个张量 ，根据下面的表达式计算 （其中  是批次维度，因此在下方的符号表示中被忽略了），其中 **LayerNorm** 和 **LinearNoBias**（无偏置线性层，只是一个权重矩阵）作用于通道维度上。

**代码版本：**

```python
# 来自 https://github.com/lucidrains/triangle-multiplicative-module/blob/main/triangle_multiplicative_module/triangle_multiplicative_module.py
class TriMul(nn.Module):
    def __init__(
        self,
        dim: int,
        hidden_dim: int,
    ):
        super().__init__()

        self.norm = nn.LayerNorm(dim)

        self.left_proj = nn.Linear(dim, hidden_dim)
        self.right_proj = nn.Linear(dim, hidden_dim)

        self.left_gate = nn.Linear(dim, hidden_dim)
        self.right_gate = nn.Linear(dim, hidden_dim)
        self.out_gate = nn.Linear(dim, hidden_dim)

        self.to_out_norm = nn.LayerNorm(hidden_dim)
        self.to_out = nn.Linear(hidden_dim, dim)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """
        x: [bs, seq_len, seq_len, dim]
        mask: [bs, seq_len, seq_len]

        Returns:
            output: [bs, seq_len, seq_len, dim]
        """
        batch_size, seq_len, _, dim = x.shape

        x = self.norm(x)
                
        # 计算左右路径
        left = self.left_proj(x)
        right = self.right_proj(x)

        mask = mask.unsqueeze(-1)
        left = left * mask
        right = right * mask

        left_gate = self.left_gate(x).sigmoid()
        right_gate = self.right_gate(x).sigmoid()
        out_gate = self.out_gate(x).sigmoid()

        left = left * left_gate
        right = right * right_gate

        # 这是你正在计算的内容： 
        # out = einsum('... i k d, ... j k d -> ... i j d', left, right)
        out = torch.zeros(batch_size, seq_len, seq_len, dim, device=x.device)
        
        # 使用嵌套循环进行计算
        for b in range(batch_size):
            for i in range(seq_len):
                for j in range(seq_len):
                    # 计算每个输出元素
                    for k in range(seq_len):
                        out[b, i, j] += left[b, i, k, :] * right[b, j, k, :]
                
        # 最终输出变换
        out = self.to_out_norm(out)
        out = out * out_gate
        return self.to_out(out)

```

**问题约束：**

* 
* 输入分布将从标准正态分布，或重尾柯西分布（）中采样。
* 可能没有掩码 (mask)，或者在输入上进行随机采样的掩码。
* 不允许使用 NVIDIA cuEquivariance 库！如果你的解决方案以任何方式使用了它，将被移出排行榜。

**备注：** 那么为什么这个问题如此令人苦恼呢？因为你必须选择是加载/处理 LayerNorms 所需的通道维度 （否则你必须进行同步来计算均值/方差等统计数据），还是处理序列维度 。序列维度特别烦人，因为它非常大，而且我们在最后的操作中计算逐对运算时，还要对另一个序列维度进行求和（这是  的复杂度！）。然而，我非常喜欢这个内核，因为它只包含“简单”的运算，而且非常容易理解。这是对 torch.compile() 做得不那么好的“算子融合 (fusions)”的真正考验。

**如果你感兴趣，这里有一些 AF3 / TriMul 内核的 GitHub 参考资料：**

[https://github.com/lucidrains/triangle-multiplicative-module](https://github.com/lucidrains/triangle-multiplicative-module)

[https://github.com/jwohlwend/boltz](https://github.com/jwohlwend/boltz)

[https://github.com/chaidiscovery/chai-lab](https://github.com/chaidiscovery/chai-lab)

[https://github.com/NVIDIA/cuEquivariance/commit/87a1ddb9fe79469a0562ce1895bdf461efc660f4](https://github.com/NVIDIA/cuEquivariance/commit/87a1ddb9fe79469a0562ce1895bdf461efc660f4)