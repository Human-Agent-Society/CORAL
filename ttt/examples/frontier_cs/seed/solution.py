"""
Example solution for cant-be-late problem.

Solution interface:
    class Solution(Strategy):
        def solve(self, spec_path: str) -> "Solution":
            # Read config from spec_path and initialize
            return self

        def _step(self, last_cluster_type, has_spot) -> ClusterType:
            # Decision logic at each simulation step
            ...
"""
import json
import math
from argparse import Namespace

from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


class Solution(Strategy):
    """Greedy strategy: stay on spot until deadline pressure dictates on-demand."""

    NAME = "greedy_safety"

    def solve(self, spec_path: str) -> "Solution":
        """Initialize the solution from spec_path config."""
        with open(spec_path) as f:
            config = json.load(f)

        # Create args object for Strategy base class
        args = Namespace(
            deadline_hours=float(config["deadline"]),
            task_duration_hours=[float(config["duration"])],
            restart_overhead_hours=[float(config["overhead"])],
            inter_task_overhead=[0.0],
        )
        super().__init__(args)
        return self

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        """Make decision at each simulation step."""
        env = self.env
        gap = env.gap_seconds

        work_left = self.task_duration - sum(self.task_done_time)
        if work_left <= 1e-9:
            return ClusterType.NONE

        left_ticks = max(0, math.floor((self.deadline - env.elapsed_seconds) / gap))
        need1d = math.ceil((work_left + self.restart_overhead) / gap)
        need2d = math.ceil((work_left + 2 * self.restart_overhead) / gap)

        # Must switch to on-demand if we can't afford any more preemptions
        if need1d >= left_ticks:
            return ClusterType.ON_DEMAND

        # Should be cautious if we can only afford one more preemption
        if need2d >= left_ticks:
            if env.cluster_type == ClusterType.SPOT and has_spot:
                return ClusterType.SPOT
            return ClusterType.ON_DEMAND

        # Otherwise, prefer spot if available
        return ClusterType.SPOT if has_spot else ClusterType.NONE
