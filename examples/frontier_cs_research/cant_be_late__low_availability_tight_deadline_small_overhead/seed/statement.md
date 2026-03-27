Cant-Be-Late Scheduling Problem
================================

Problem Setting
--------

You are given a long-running compute job that must complete before a fixed **hard deadline**.
At each time step, you must choose which type of cloud compute resource to use:

- **Spot instances**
  - Very cheap
  - May become unavailable at certain timesteps
  - Can be preempted at any time, the job will incur a **restart overhead**

- **On-demand instances**
  - Guaranteed available
  - Expensive
  - Never interrupted

Your strategy must decide at every timestep whether to use Spot, use On-Demand, or pause (NONE).

Restart overheads do not stack: launching a new instance while an old overhead is still pending will replace the previous remaining restart overhead with the new one.

Your goal is to **finish before the deadline** while **minimizing cost**.

The evaluation uses many real spot-availability traces.

---

API Specification
-----------------

Implement a `Solution` class that inherits from `Strategy`:

```python
from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType

class Solution(Strategy):
    NAME = "my_solution"  # REQUIRED: unique identifier

    def solve(self, spec_path: str) -> "Solution":
        """
        Optional initialization. Called once before evaluation.
        Read spec_path for configuration if needed.
        Must return self.
        """
        return self

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        """
        Called at each time step. Return which cluster type to use next.

        Args:
            last_cluster_type: The cluster type used in the previous step
            has_spot: Whether spot instances are available this step

        Returns:
            ClusterType.SPOT, ClusterType.ON_DEMAND, or ClusterType.NONE
        """
        # Your decision logic here
        if has_spot:
            return ClusterType.SPOT
        return ClusterType.ON_DEMAND

    @classmethod
    def _from_args(cls, parser):  # REQUIRED: For evaluator instantiation
        args, _ = parser.parse_known_args()
        return cls(args)
```

Available Attributes in `_step`:
- `self.env.elapsed_seconds`: Current time elapsed (seconds)
- `self.env.gap_seconds`: Time step size (seconds)
- `self.env.cluster_type`: Current cluster type
- `self.task_duration`: Total task duration needed (seconds)
- `self.task_done_time`: List of completed work segments
- `self.deadline`: Deadline time (seconds)
- `self.restart_overhead`: Time overhead when restarting (seconds)

ClusterType Values:
- `ClusterType.SPOT`: Use spot instance
- `ClusterType.ON_DEMAND`: Use on-demand instance
- `ClusterType.NONE`: Do nothing this step (no cost)

Scoring (0-100)
---------------
```
OD_anchor = Cost of running fully on-demand (baseline upper bound)
SPOT_anchor = Cost of running fully on spot (baseline lower bound)
AvgCost = Your strategy's average cost

normalized_score = (OD_anchor - AvgCost) / (OD_anchor - SPOT_anchor)
score = clip(normalized_score, 0, 1) × 100
```

If you fail to finish before the deadline, you receive a penalty score of -100000.

Evaluation Details
------------------
- Tested on real Spot instance traces
- Task duration: 48 hours
- Deadline: 52 hours (4-hour slack)
- Restart overhead: 0.05 hours (3 minutes)
- Price of on-demand: ~3.06$/hr
- Price of Spot: ~0.97$/hr
- Regions: Low availability (4-40%)

Your program has a total time limit of 300 seconds.

Implementation Notes
---------------------
**Required Elements:**
- `NAME` attribute must be defined on your Solution class
- `_from_args` classmethod must be implemented
- `solve()` must return `self`
- `_step()` must not return `ClusterType.SPOT` when `has_spot=False`

