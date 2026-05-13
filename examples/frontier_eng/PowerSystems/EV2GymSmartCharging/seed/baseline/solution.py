from __future__ import annotations

import json
from typing import Any


# EVOLVE-BLOCK-START

def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def _desired_capacity_action(port: dict[str, Any], timescale_minutes: float) -> float:
    if not bool(port.get("connected", False)):
        return 0.0

    charger_limit_kw = max(0.0, float(port.get("charger_max_power_kw", 0.0)))
    ev_limit_kw = max(0.0, float(port.get("max_ac_charge_power_kw", 0.0)))
    max_power_to_charge_kw = min(charger_limit_kw, ev_limit_kw)
    if charger_limit_kw <= 0.0 or max_power_to_charge_kw <= 0.0:
        return 0.0

    current_capacity_kwh = float(port.get("current_capacity_kwh", 0.0))
    desired_capacity_kwh = float(port.get("desired_capacity_kwh", current_capacity_kwh))
    max_energy_to_charge_kwh = max_power_to_charge_kw * timescale_minutes / 60.0

    if current_capacity_kwh + max_energy_to_charge_kwh < desired_capacity_kwh:
        return 1.0

    residual_kwh = desired_capacity_kwh - current_capacity_kwh
    action = residual_kwh * 60.0 / timescale_minutes / charger_limit_kw
    return max(0.0, action)


def solve(case: dict[str, Any], max_sim_calls: int = 0, simulate_fn: Any | None = None) -> dict[str, Any]:
    # Do not change: keep the evaluation entrypoint signature and return format.
    # You may change: replace this with a stronger policy as long as the interface contract is preserved.
    del max_sim_calls, simulate_fn

    timescale_minutes = float(case.get("timescale_minutes", 15.0))
    ports = list(case.get("ports", []))
    actions = [
        _clip(_desired_capacity_action(port, timescale_minutes), -1.0, 1.0)
        for port in ports
    ]

    return {
        "actions": actions,
        "meta": {
            "policy": "ev2gym_charge_as_fast_as_possible_to_desired_capacity",
            "current_step": int(case.get("current_step", 0)),
            "num_ports": len(actions),
        },
    }


# EVOLVE-BLOCK-END


if __name__ == "__main__":
    print(json.dumps({"message": "Use verification/evaluator.py to score this policy."}))
