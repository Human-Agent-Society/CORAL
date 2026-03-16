"""Heartbeat: registered actions with independent intervals."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class HeartbeatAction:
    """A registered heartbeat action with its own interval and prompt."""

    name: str  # e.g. "reflect", "consolidate"
    every: int  # trigger every N evals
    prompt: str  # rendered prompt string
    is_global: bool = False  # True = use global eval count, False = per-agent


class HeartbeatRunner:
    """Check registered actions against eval counts."""

    def __init__(self, actions: list[HeartbeatAction]) -> None:
        self.actions = actions

    def check(self, *, local_eval_count: int, global_eval_count: int) -> list[HeartbeatAction]:
        """Return all actions whose interval matches the appropriate eval count."""
        triggered = []
        for action in self.actions:
            count = global_eval_count if action.is_global else local_eval_count
            if count > 0 and count % action.every == 0:
                triggered.append(action)
        return triggered
