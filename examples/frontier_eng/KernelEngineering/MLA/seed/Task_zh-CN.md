# 描述

您将实现一个针对 MI300 优化的自定义 MLA 解码内核，以下是一些简化之处：

1. Q、K、V 数据类型为 bfloat16

2. 仅使用预分配的非分页潜在键值缓存进行解码

3. 返回带有 MLA 输出的更新 kv 缓存

张量的所有外维度和内维度的形状均来自 DeepSeek-R1，并且为了适应单个 GPU，分配了多个计算头。具体来说，您将获得一个张量元组：

```
input [bs, sq, dim]
attn_output [bs, n_heads, sq, v_head_dim]
kv_cache [bs, sq, kv_lora_rank + qk_rope_head_dim]
```

在这里

0. bs::128 # 批处理大小
1. prefill::[512, 2048, 4096, 6144] # 作为 kv 长度
2. sq::1 # 仅考虑解码
3. dim::7168 # deepseek v3 的隐藏大小
4. kv_lora_rank::[512] # deepseek v3 的 kv lora 排名
5. qk_rope_head_dim::[64] # 绳索嵌入维度
6. v_head_dim::128 # 头部尺寸
7. n_heads::128 # 注意力头数量

排名标准是基准测试结果的几何平均值。

对于大奖，你的内核将根据光速分析进行评估，最接近光速的解决方案将获得大奖。

光速分析如下：

| **bs** | **prefill sq** | **dtype** | **roofline time(us)** |
| :--- | :--- | :--- | :--- |
| 128 | 512 | bf16 | 54.62 |
| 128 | 2048 | bf16 | 141.16 |
| 128 | 4096 | bf16 | 210.75 |
| 128 | 6144 | bf16 | 280.87 |