VDB Design Problem - Recall80 Latency Tier
===========================================

Problem Setting
---------------
Design a Vector Database index optimized for **latency** subject to a **recall constraint**. This tier uses recall-gated scoring: solutions failing to meet the recall threshold receive zero points, while solutions meeting the constraint are scored purely by latency.

**Optimization Goal**: Minimize latency within recall constraint

$$
\text{score} = \begin{cases}
0 & \text{if } r < r_{\text{gate}} \\
100 & \text{if } r \geq r_{\text{gate}} \text{ and } t_{\text{query}} \leq t_{\text{min}} \\
100 \cdot \frac{t_{\text{max}} - t_{\text{query}}}{t_{\text{max}} - t_{\text{min}}} & \text{if } r \geq r_{\text{gate}} \text{ and } t_{\text{min}} < t_{\text{query}} < t_{\text{max}} \\
0 & \text{if } r \geq r_{\text{gate}} \text{ and } t_{\text{query}} \geq t_{\text{max}}
\end{cases}
$$

Where:
- $r$: Your recall@1
- $t_{\text{query}}$: Your average query latency (ms)
- $r_{\text{gate}} = 0.80$ (minimum required recall)
- $t_{\text{min}} = 0.0\text{ms}$ (best possible latency)
- $t_{\text{max}} = 0.6\text{ms}$ (maximum allowed latency)

**Key Insight**: Unlike other tiers, this tier gates on recall and scores on latency. You MUST achieve ≥80% recall, then faster is better.

Baseline Performance
--------------------
- Recall@1: **0.9914** (99.14%)
- Avg query time: **3.85ms**

Scoring Examples
----------------
All examples assume recall constraint is met ($r \geq 0.80$):

| Recall@1 | Latency | Score Calculation | Score |
|----------|---------|-------------------|-------|
| 0.85 | 0.00ms | $t \leq t_{\text{min}}$ → max score | **100** |
| 0.85 | 0.30ms | $\frac{0.6 - 0.3}{0.6 - 0.0} = 0.50$ | **50** |
| 0.82 | 0.50ms | $\frac{0.6 - 0.5}{0.6 - 0.0} = 0.167$ | **16.7** |
| 0.90 | 0.10ms | $\frac{0.6 - 0.1}{0.6 - 0.0} = 0.833$ | **83.3** |
| **0.75** | 0.20ms | $r < r_{\text{gate}}$ → recall gate fails | **0** |
| 0.95 | **0.70ms** | $t \geq t_{\text{max}}$ → latency too high | **0** |

**Note**: This is the most aggressive latency requirement (0.6ms max). You must use extreme approximation while maintaining 80% recall.

API Specification
-----------------
Implement a class with the following interface:

```python
import numpy as np
from typing import Tuple

class YourIndexClass:
    def __init__(self, dim: int, **kwargs):
        """
        Initialize the index for vectors of dimension `dim`.

        Args:
            dim: Vector dimensionality (e.g., 128 for SIFT1M)
            **kwargs: Optional parameters (e.g., M, ef_construction for HNSW)

        Example:
            index = YourIndexClass(dim=128, nlist=256, nprobe=2)
        """
        pass

    def add(self, xb: np.ndarray) -> None:
        """
        Add vectors to the index.

        Args:
            xb: Base vectors, shape (N, dim), dtype float32

        Notes:
            - Can be called multiple times (cumulative)
            - Must handle large N (e.g., 1,000,000 vectors)

        Example:
            index.add(xb)  # xb.shape = (1000000, 128)
        """
        pass

    def search(self, xq: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for k nearest neighbors of query vectors.

        Args:
            xq: Query vectors, shape (nq, dim), dtype float32
            k: Number of nearest neighbors to return

        Returns:
            (distances, indices):
                - distances: shape (nq, k), dtype float32, L2 distances
                - indices: shape (nq, k), dtype int64, indices into base vectors

        Notes:
            - Must return exactly k neighbors per query
            - Indices should refer to positions in the vectors passed to add()
            - Lower distance = more similar

        Example:
            D, I = index.search(xq, k=1)  # xq.shape = (10000, 128)
            # D.shape = (10000, 1), I.shape = (10000, 1)
        """
        pass
```

**Implementation Requirements**:
- Class can have any name (evaluator auto-discovers classes with `add` and `search` methods)
- Must handle SIFT1M dataset: 1M base vectors, 10K queries, 128 dimensions
- Your `search` must return tuple `(distances, indices)` with shapes `(nq, k)`
- Distances should be L2 (Euclidean) or L2-squared
- No need to handle dataset loading - evaluator provides numpy arrays

Evaluation Process
------------------
The evaluator follows these steps:

### 1. Load Dataset
```python
from faiss.contrib.datasets import DatasetSIFT1M
ds = DatasetSIFT1M()
xb = ds.get_database()        # (1000000, 128) float32
xq = ds.get_queries()         # (10000, 128) float32
gt = ds.get_groundtruth()     # (10000, 100) int64 - ground truth indices
```

### 2. Build Index
```python
from solution import YourIndexClass  # Auto-discovered
d = xb.shape[1]                       # 128 for SIFT1M
index = YourIndexClass(d)             # Pass dimension as first argument
index.add(xb)                         # Add all 1M base vectors
```

### 3. Measure Performance (Batch Queries)
```python
import time
t0 = time.time()
D, I = index.search(xq, k=1)          # Search all 10K queries at once
t1 = time.time()

# Calculate metrics
recall_at_1 = (I[:, :1] == gt[:, :1]).sum() / len(xq)
avg_query_time_ms = (t1 - t0) * 1000.0 / len(xq)
```

**Important**: `avg_query_time_ms` from **batch queries** is used for scoring. Batch queries benefit from CPU cache and vectorization, typically faster than single queries.

### 4. Calculate Score
```python
if recall_at_1 < 0.80:
    score = 0.0
elif avg_query_time_ms <= 0.0:
    score = 100.0
elif avg_query_time_ms >= 0.6:
    score = 0.0
else:
    proportion = (avg_query_time_ms - 0.0) / (0.6 - 0.0)
    score = 100.0 * (1.0 - proportion)
```

Dataset Details
---------------
- **Name**: SIFT1M
- **Base vectors**: 1,000,000 vectors of dimension 128
- **Query vectors**: 10,000 vectors
- **Ground truth**: Precomputed nearest neighbors (k=1)
- **Metric**: L2 (Euclidean distance)
- **Vector type**: float32

Runtime Platform
----------------
- **Infrastructure**: Evaluations run on SkyPilot-managed cloud instances (AWS, GCP, or Azure)
- **Compute**: CPU-only instances (no GPU required)
- **Environment**: Docker containerized execution with Python 3, NumPy ≥1.24, FAISS-CPU ≥1.7.4

Constraints
-----------
- **Timeout**: 1 hour for entire evaluation (index construction + queries)
- **Memory**: Use reasonable memory (index should fit in RAM)
- **Recall constraint**: recall@1 ≥ 0.80
- **Latency range**: 0.0ms ≤ avg_query_time_ms ≤ 0.6ms

Strategy Tips
-------------
1. **Meet recall gate first**: Ensure ≥80% recall, otherwise score = 0
2. **Extreme approximation**: Use minimal search budget (IVF nprobe=1-3)
3. **Batch optimization critical**: 0.6ms is extremely tight, every microsecond counts
4. **Trade recall for speed**: 80-85% recall with ultra-low latency is ideal

Example: Simple Baseline
-------------------------
```python
import numpy as np

class SimpleIndex:
    def __init__(self, dim: int, **kwargs):
        self.dim = dim
        self.xb = None

    def add(self, xb: np.ndarray) -> None:
        if self.xb is None:
            self.xb = xb.copy()
        else:
            self.xb = np.vstack([self.xb, xb])

    def search(self, xq: np.ndarray, k: int) -> tuple:
        # Compute all pairwise L2 distances
        # xq: (nq, dim), xb: (N, dim)
        # distances: (nq, N)
        distances = np.sqrt(((xq[:, np.newaxis, :] - self.xb[np.newaxis, :, :]) ** 2).sum(axis=2))

        # Get k nearest neighbors
        indices = np.argpartition(distances, k-1, axis=1)[:, :k]
        sorted_indices = np.argsort(distances[np.arange(len(xq))[:, None], indices], axis=1)
        final_indices = indices[np.arange(len(xq))[:, None], sorted_indices]
        final_distances = distances[np.arange(len(xq))[:, None], final_indices]

        return final_distances, final_indices
```

**Note**: This baseline achieves perfect recall (100%) but is too slow for large datasets. Use approximate methods like HNSW, IVF, or LSH for better speed-recall tradeoffs.

Debugging Tips
--------------
- **Test locally**: Use a subset of data (e.g., 10K vectors) for faster iteration
- **Verify shapes**: Ensure `search` returns `(nq, k)` shaped arrays
- **Check recall calculation**: `(I[:, :1] == gt[:, :1]).sum() / len(xq)`
- **Profile latency**: Measure batch vs single query performance separately
- **Validate before submit**: Run full 1M dataset locally if possible
