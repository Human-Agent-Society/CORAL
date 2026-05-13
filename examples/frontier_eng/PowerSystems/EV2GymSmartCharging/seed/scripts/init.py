from __future__ import annotations

import json
from typing import Any


# EVOLVE-BLOCK-START

def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def _charge_as_fast_as_possible(port: dict[str, Any]) -> float:
    if not bool(port.get("connected", False)):
        return 0.0
    charger_limit_kw = max(0.0, float(port.get("charger_max_power_kw", 0.0)))
    ev_limit_kw = max(0.0, float(port.get("max_ac_charge_power_kw", 0.0)))
    if min(charger_limit_kw, ev_limit_kw) <= 0.0:
        return 0.0
    return 1.0


def solve(case: dict[str, Any], max_sim_calls: int = 0, simulate_fn: Any | None = None) -> dict[str, Any]:
    # DO NOT MODIFY: keep the evaluation entrypoint signature and return format.
    # MODIFIABLE: improve the action policy using EV, transformer, price, and future information from `case`.
    del max_sim_calls, simulate_fn

    ports = list(case.get("ports", []))
    actions = [_clip(_charge_as_fast_as_possible(port), -1.0, 1.0) for port in ports]

    return {
        "actions": actions,
        "meta": {
            "policy": "ev2gym_charge_as_fast_as_possible",
            "current_step": int(case.get("current_step", 0)),
            "num_ports": len(actions),
        },
    }


# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(json.dumps({"message": "Use verification/evaluator.py to score this policy."}))
