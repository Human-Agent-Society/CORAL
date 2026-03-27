Ragged Attention Optimization Problem
======================================

Problem Setting
---------------
Design and optimize high-performance Triton kernels for ragged attention computation on GPU. This problem focuses on implementing efficient kernels that handle variable-length sequences using ragged attention, where each query row can attend to a different number of key/value rows.

The challenge involves optimizing:
- **Ragged attention**: Efficiently handling variable-length sequences where each row has different attention lengths
- **Memory access patterns**: Efficient loading and storing of Q, K, V tensors with ragged masking
- **Streaming softmax**: Computing softmax in a streaming fashion for numerical stability
- **Row-wise masking**: Correctly masking attention scores based on row_lens
- **Mixed precision**: Handling float16 inputs/outputs with float32 accumulation
- **Block tiling**: Optimal block sizes for GPU execution across different matrix sizes
- **Performance benchmarking**: Achieving speedup over baseline PyTorch implementations

Target
------
- **Primary**: Maximize geometric mean speedup over baseline (higher is better)
- **Secondary**: Ensure correctness across diverse matrix sizes and ragged lengths
- **Tertiary**: Minimize kernel launch overhead and memory usage

API Specification
-----------------
Implement a `Solution` class that returns a Triton kernel implementation:

```python
class Solution:
    def solve(self, spec_path: str = None) -> dict:
        """
        Returns a dict with either:
        - {"code": "python_code_string"}
        - {"program_path": "path/to/kernel.py"}
        """
        # Your implementation
        pass
```

Your kernel implementation must provide:

```python
import torch
import triton
import triton.language as tl

def ragged_attn(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, row_lens: torch.Tensor) -> torch.Tensor:
    """
    Ragged attention computation.
    
    Args:
        Q: Query tensor of shape (M, D) - query features (float16)
        K: Key tensor of shape (N, D) - key features (float16)
        V: Value tensor of shape (N, Dv) - value features (float16)
        row_lens: Row lengths tensor of shape (M,) - number of valid K/V rows per Q row (int32 or int64)
    
    Returns:
        Output tensor of shape (M, Dv) - attention output (float16)
    
    Semantics:
        For each query row i (0 <= i < M), compute attention over the first row_lens[i] key/value rows.
        Specifically:
        - scores[i, j] = (Q[i] @ K[j].T) * scale, for j < row_lens[i], else -inf
        - P[i] = softmax(scores[i])
        - O[i] = P[i] @ V[:row_lens[i]]
    """
    pass
```

Scoring
-------
The scoring system evaluates your implementation based on geometric mean speedup over GPU baseline:

- **0 points**: 1x GPU baseline (same speed as PyTorch GPU baseline)
- **100 points**: 3x GPU baseline (3x speedup over PyTorch GPU baseline)
- **Linear interpolation**: Scores between 0-100 are linearly interpolated based on speedup

The evaluation uses the following test cases:
- M (number of query rows): [512, 1024]
- N (number of key/value rows): 1024
- D (model dimension): 64
- Dv (value dimension): 64
- row_lens: Random integers between [min_ratio*N, N] where min_ratio=0.25

Correctness is verified using:
- Relative tolerance: 1e-2
- Absolute tolerance: 5e-3

All tests must pass for a non-zero score. If any test fails correctness, the score is 0.

Example
-------
```python
import torch
import triton
import triton.language as tl

@triton.jit
def _ragged_kernel(Q, K, V, O, ROW_LENS, ...):
    # Your kernel implementation
    pass

def ragged_attn(Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, row_lens: torch.Tensor) -> torch.Tensor:
    # Your kernel launch logic
    pass
```

Constraints
-----------
- All tensors must be CUDA tensors (float16 for Q, K, V; int32/int64 for row_lens)
- Output must be float16
- The implementation must handle variable row lengths correctly
- Accumulation should use float32 for numerical stability
- Must use streaming softmax for numerical stability

Tips
----
1. Use efficient block tiling (BM, BN, BD, BDV) for optimal performance
2. Implement streaming softmax to handle large attention matrices
3. Correctly mask attention scores based on row_lens
4. Load row_lens once per program and broadcast for masking
5. Use proper masking for boundary conditions

