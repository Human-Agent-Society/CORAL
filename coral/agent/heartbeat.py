"""Heartbeat: registered actions with independent intervals and plateau detection."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class HeartbeatAction:
    """A registered heartbeat action with its own interval and prompt.

    Actions can trigger on a fixed interval (``trigger="interval"``) or when the
    agent's score has not improved for a number of consecutive evals
    (``trigger="plateau"``).  Plateau actions use ``every`` as the number of
    non-improving evals required before firing, and include a cooldown so they
    don't re-fire until the agent improves or another ``every`` evals pass.
    """

    name: str  # e.g. "reflect", "consolidate", "pivot"
    every: int  # interval evals (interval) or stall threshold (plateau)
    prompt: str  # rendered prompt string
    is_global: bool = False  # True = use global eval count, False = per-agent
    trigger: str = "interval"  # "interval" or "plateau"


class HeartbeatRunner:
    """Check registered actions against eval counts and plateau state."""

    def __init__(self, actions: list[HeartbeatAction]) -> None:
        self.actions = actions
        # Track when each plateau action last fired so we don't spam
        self._plateau_fired_at: dict[str, int] = {}

    def check(
        self,
        *,
        local_eval_count: int,
        global_eval_count: int,
        evals_since_improvement: int = 0,
    ) -> list[HeartbeatAction]:
        """Return all actions whose trigger condition is met.

        Args:
            local_eval_count: This agent's total eval count.
            global_eval_count: Total evals across all agents.
            evals_since_improvement: How many consecutive evals this agent has
                gone without a personal-best score improvement.
        """
        triggered = []
        for action in self.actions:
            if action.trigger == "plateau":
                if self._check_plateau(action, evals_since_improvement):
                    triggered.append(action)
            else:
                count = global_eval_count if action.is_global else local_eval_count
                if count > 0 and count % action.every == 0:
                    triggered.append(action)
        return triggered

    def _check_plateau(self, action: HeartbeatAction, evals_since_improvement: int) -> bool:
        """Check if a plateau action should fire.

        Fires when ``evals_since_improvement >= action.every`` and enough evals
        have passed since the last time this action fired (cooldown = every).
        """
        if evals_since_improvement < action.every:
            # Not stuck long enough — also reset if agent improved
            if evals_since_improvement == 0:
                self._plateau_fired_at.pop(action.name, None)
            return False

        last_fired = self._plateau_fired_at.get(action.name)
        if last_fired is not None:
            # Cooldown: don't re-fire until another `every` evals of stalling
            if evals_since_improvement - last_fired < action.every:
                return False

        self._plateau_fired_at[action.name] = evals_since_improvement
        return True
