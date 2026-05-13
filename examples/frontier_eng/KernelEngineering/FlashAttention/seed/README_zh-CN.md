# FlashAttention

为 GPU 执行优化因果型 scaled dot-product attention 前向内核。
该基准会在长序列上评估 bfloat16 多头注意力的数值正确性和运行时间。

## 文件结构

```text
FlashAttention/
├── README.md
├── Task.md
├── baseline/
│   ├── reference.py
│   ├── submission.py
│   ├── task.py
│   ├── task.yml
│   └── utils.py
└── verification/
    ├── eval.py
    ├── flash_attn_tests.txt
    ├── flash_attn_bench.txt
    └── requirements-gpumode.txt
```

## 快速开始

### 1. 安装依赖

使用支持 CUDA 的 PyTorch 与 Triton 的 Python 环境，然后安装：

```bash
pip install -r verification/requirements-gpumode.txt
```

### 2. 实现内核

编辑 `baseline/submission.py`，将 `custom_kernel(data)` 替换为你的优化实现。

### 3. 运行正确性测试

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_tests.log
POPCORN_FD=3 python eval.py test flash_attn_tests.txt
```

### 4. 运行性能基准

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_bench.log
POPCORN_FD=3 python eval.py benchmark flash_attn_bench.txt
```

### 5. 运行排行榜风格复检

```bash
cd benchmarks/KernelEngineering/FlashAttention/verification

exec 3>flash_attn_leaderboard.log
POPCORN_FD=3 python eval.py leaderboard flash_attn_bench.txt
```

## 提交接口

你的候选实现必须暴露：

```python
def custom_kernel(data):
    ...
```

其中 `data` 是一个四元组：

```python
(config, Q, K, V)
```

返回值是形状为以下形式的注意力输出张量：

```python
[batch_size, n_heads, seq_len_q, head_dim]
```

## 任务摘要

- **运算**: 因果型 scaled dot-product attention 前向计算
- **数据类型**: `torch.bfloat16`
- **标准形状**:
  - `Q`: `[B, H, S_q, D]`
  - `K`: `[B, H, S_kv, D]`
  - `V`: `[B, H, S_kv, D]`
  - 输出: `[B, H, S_q, D]`
- **主要配置**:
  - `batch_size = 4`
  - `n_heads = 32`
  - `head_dim = 128`
  - `causal = True`
- **正确性用例**: `verification/flash_attn_tests.txt` 中 `S ∈ {512, 1024, 2048}`
- **基准文件**: `verification/flash_attn_bench.txt`

## 评分

- 数值正确性会与 `torch.nn.functional.scaled_dot_product_attention` 对比。
- 运行时间由 `verification/eval.py` 以纳秒计量。
- 运行时间越低越好。
- 在 `frontier_eval` 中，可行运行会映射为 `combined_score = 1e9 / geom_mean_ns`，因此分数越高越好。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=KernelEngineering/FlashAttention`

```bash
python -m frontier_eval \
task=unified task.benchmark=KernelEngineering/FlashAttention \
task.runtime.conda_env=kernel \
algorithm.iterations=10
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=flash_attention`。
