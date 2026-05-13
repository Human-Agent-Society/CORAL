# FlashAttention

## 1. 问题

实现一个优化后的因果型 scaled dot-product attention 前向内核。
评测器会提供 query、key、value 张量，并将你的输出与 PyTorch 参考实现进行比较。

## 2. 输入与输出

`custom_kernel` 的输入为：

```python
(config, Q, K, V)
```

其中：

- `Q`: `[batch_size, n_heads, seq_len_q, head_dim]`
- `K`: `[batch_size, n_heads, seq_len_kv, head_dim]`
- `V`: `[batch_size, n_heads, seq_len_kv, head_dim]`
- dtype: `torch.bfloat16`

输出必须是：

- 形状为 `[batch_size, n_heads, seq_len_q, head_dim]` 的注意力结果

`config` 包含：

- `batch_size`
- `n_heads`
- `seq_len_q`
- `seq_len_kv`
- `head_dim`
- `causal`
- `scale = 1 / sqrt(head_dim)`

## 3. 基准设置

提供的基准配置目标为：

- `batch_size = 4`
- `n_heads = 32`
- `head_dim = 128`
- `causal = True`
- 序列长度：
  - 正确性测试：`512`、`1024`、`2048`
  - 基准文件当前包含：`2048`

注意力计算等价于：

```python
scores = (Q @ K.transpose(-1, -2)) * scale
scores = scores + causal_mask
attn = softmax(scores, dim=-1)
out = attn @ V
```

但高性能方案应尽可能避免显式物化完整注意力矩阵。

## 4. 目标

在保持数值正确性的前提下最小化执行时间。

## 5. 正确性规则

你的实现会与 `baseline/reference.py` 对比，该文件调用：

```python
torch.nn.functional.scaled_dot_product_attention(...)
```

提供的检查器使用近似容差匹配，因此输出必须与参考结果数值接近。

## 6. 允许修改范围

你应当修改：

- `baseline/submission.py`

不应修改评测契约、文件名或测试规格格式。

## 7. 评测命令

在 `benchmarks/KernelEngineering/FlashAttention/verification` 目录下运行：

### 正确性

```bash
exec 3>flash_attn_tests.log
POPCORN_FD=3 python eval.py test flash_attn_tests.txt
```

### 基准测试

```bash
exec 3>flash_attn_bench.log
POPCORN_FD=3 python eval.py benchmark flash_attn_bench.txt
```

### 排行榜风格重复校验

```bash
exec 3>flash_attn_leaderboard.log
POPCORN_FD=3 python eval.py leaderboard flash_attn_bench.txt
```

## 8. 评分

- 若任一 case 的正确性失败，该次运行无效。
- 有效运行会输出每个基准 case 的计时统计。
- 基准按运行时间几何平均值进行排名。
- 在 `frontier_eval` 中，有效结果会映射为 `combined_score = 1e9 / geom_mean_ns`，因此内核越快分数越高。

## 9. 参考

- 参考实现：`baseline/reference.py`
- 候选模板：`baseline/submission.py`
- 评测器：`verification/eval.py`
- 基准规格：`baseline/task.yml`
