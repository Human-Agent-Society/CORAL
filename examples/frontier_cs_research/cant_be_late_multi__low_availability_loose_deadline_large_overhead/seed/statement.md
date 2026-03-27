Cant-Be-Late Multi-Region Scheduling Problem
================================

Problem Setting
---------------

You are given a long-running compute job that must complete before a fixed hard deadline.
At each time step, you must choose which AWS region to run in and which type of cloud compute resource to use:

- **Spot instances**  
  - Very cheap  
  - May become unavailable at certain timesteps  
  - Can be preempted at any time, the job will incur a **restart overhead**

- **On-demand instances**
  - Guaranteed available  
  - Expensive  
  - Never interrupted

- **Multi-region execution**
  - You may switch to another AWS region at any timestep
  - Switching regions forces a restart overhead (same as losing the work of the current timestep)
  - Spot availability differs per region based on real traces

Your strategy must decide at every timestep whether to use Spot, use On-Demand, or pause (NONE).

Your strategy can also switch to a different region at each step.

Restart overheads do not stack: launching a new instance while an old overhead is still pending will replace the previous remaining restart overhead with the new one.

Your goal is to **finish before the deadline** while **minimizing cost**.


The evaluation uses many real spot-availability traces.
---

API Specification
-----------------

Implement a `Solution` class that extends `MultiRegionStrategy`:

```python
import json
from argparse import Namespace

from sky_spot.strategies.multi_strategy import MultiRegionStrategy
from sky_spot.utils import ClusterType


class Solution(MultiRegionStrategy):
    """Your multi-region scheduling strategy."""

    NAME = "my_strategy"  # REQUIRED: unique identifier

    def solve(self, spec_path: str) -> "Solution":
        """
        Initialize the solution from spec_path config.

        The spec file contains:
        - deadline: deadline in hours
        - duration: task duration in hours
        - overhead: restart overhead in hours
        - trace_files: list of trace file paths (one per region)
        """
        with open(spec_path) as f:
            config = json.load(f)

        args = Namespace(
            deadline_hours=float(config["deadline"]),
            task_duration_hours=[float(config["duration"])],
            restart_overhead_hours=[float(config["overhead"])],
            inter_task_overhead=[0.0],
        )
        super().__init__(args)
        return self

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        """
        Decide next action based on current state.

        Available attributes:
        - self.env.get_current_region(): Get current region index
        - self.env.get_num_regions(): Get total number of regions
        - self.env.switch_region(idx): Switch to region by index
        - self.env.elapsed_seconds: Current time elapsed
        - self.task_duration: Total task duration needed (seconds)
        - self.deadline: Deadline time (seconds)
        - self.restart_overhead: Restart overhead (seconds)
        - self.task_done_time: List of completed work segments
        - self.remaining_restart_overhead: Current pending overhead

        Returns: ClusterType.SPOT, ClusterType.ON_DEMAND, or ClusterType.NONE
        """
        # Your decision logic here
        if has_spot:
            return ClusterType.SPOT
        return ClusterType.ON_DEMAND
```

Parameters:
---------------
### ClusterType:
ClusterType has 3 members: 

ClusterType.SPOT: Spot type cluster.

ClusterType.ON_DEMAND: On Demand type cluster.

ClusterType.None: None, no cluster.

#### You are given some fixed parameters:

env.gap_seconds: The size of each time step, in seconds.

task_duration: The total amount of work time required to finish the task (in seconds).

deadline: The task’s deadline (in seconds).

restart_overhead: The time overhead incurred when a job restarts.

You should implement the function to return the next cluster type to use as described above.

####  At each time step, you are given:

env.elapsed_seconds: Current time elapsed (in second).

env.cluster_type: The current cluster type running your task.

task_done_time: A list of completed work segments, where sum(self.task_done_time) = the amount of successful work time accumulated so far.

has_spot: A boolean indicating whether the Spot cluster is available in the current time step. If False, the strategy must not return ClusterType.SPOT (doing so will raise an error).

### You can use:

env.get_current_region(): Get your current region index (0-8).

env.switch_region(idx): Switch to region by index (no cost).

#### You should return:

ClusterType.SPOT: if you want to run the next time step on the Spot cluster.

ClusterType.ON_DEMAND: if you want to run the next time step on the On-Demand cluster.

ClusterType.NONE: if you choose not to run on any cluster during the next time step; this incurs no cost.

Scoring
-------
```
combined_score = -average_cost_across_all_scenarios
```

Negative cost: Lower cost = higher (less negative) score.

Notice that if you fail to finish the task before the deadline, you will receive a penalty score of -100000.

Evaluation Details
------------------
**Stage 1**: Quick check on 2-region scenario (must pass to proceed)  
**Stage 2**: Full evaluation on 4 scenarios:
- 2 zones west (8 traces)
- 3 zones west (6 traces)
- 2 regions west-east2 (8 traces)
- 5 regions mixed (4 traces)


- Task duration: 24 hours
- Deadline: 48 hours (24-hour slack)
- Restart overhead: 0.20 hours (12 minutes)
- Price of on-demand is 3.06$/hr
- Price of Spot is 0.9701$/hr

- Notice your solution will be tested on real traces with low Spot availability.

Your program has a total time limit of 300 seconds. You may be evaluated for up to 36 × 60 × 60 = 129600 time steps. Please ensure that your code is efficient under python.

Implementation Notes
---------------------
**Required Elements (Missing these will cause evaluation failures):**
- `NAME` attribute must be defined on your Solution class
- `solve(self, spec_path)` method must initialize the strategy and return `self`
- `_step(self, last_cluster_type, has_spot)` method must return a ClusterType
- Ensure proper handling of ClusterType.NONE return values



Concrete Step Example:
----------------------
Here is a concrete example demonstrating our environment.
Assume we are:
```
Parameter                | Value
-------------------------|------------------------
env.gap_seconds          | 3600.0
env.elapsed_seconds      | 18000
task_done_time           | [3600, 3600, 2880, 3600, 3600]
has_spot                 | True
env.cluster_type         | ClusterType.SPOT
env.get_current_region() | 0
```
If we use env.switch_region(1), we will have:
```
Parameter                | Value
-------------------------|------------------------
env.gap_seconds          | 3600.0
env.elapsed_seconds      | 18000
task_done_time           | [3600, 3600, 2880, 3600, 3600]
has_spot                 | True
env.cluster_type         | ClusterType.SPOT
env.get_current_region() | 1
```
If our strategy returns ClusterType.ON_DEMAND, there will be a restart overhead:
```
Parameter                | Value
-------------------------|------------------------
env.gap_seconds          | 3600.0
env.elapsed_seconds      | 23400
task_done_time           | [3600, 3600, 2880, 3600, 3600, 2880]
has_spot                 | True
env.cluster_type         | ClusterType.ON_DEMAND
env.get_current_region() | 1
```
If our strategy returns ClusterType.SPOT:
```
Parameter                | Value
-------------------------|------------------------
env.gap_seconds          | 3600.0
env.elapsed_seconds      | 21600
task_done_time           | [3600, 3600, 2880, 3600, 3600, 3600]
has_spot                 | True
env.cluster_type         | ClusterType.SPOT
env.get_current_region() | 1
```