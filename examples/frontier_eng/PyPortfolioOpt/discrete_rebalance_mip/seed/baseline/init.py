# EVOLVE-BLOCK-START
import numpy as np


def _objective(x, unit, target_dollar, current_lots, fee_rate):
    holding = unit * x
    traded = unit * np.abs(x - current_lots)
    traded_notional = traded.sum()
    return float(np.abs(holding - target_dollar).sum() + fee_rate * traded_notional)


def _violations(x, unit, current_lots, fee_rate, portfolio_value, turnover_limit_value):
    traded_notional = float((unit * np.abs(x - current_lots)).sum())
    spend = float((unit * x).sum() + fee_rate * traded_notional)
    v_budget = max(0.0, spend - portfolio_value)
    v_turn = max(0.0, traded_notional - turnover_limit_value)
    return v_budget, v_turn


def _is_feasible(x, unit, current_lots, fee_rate, portfolio_value, turnover_limit_value):
    vb, vt = _violations(
        x, unit, current_lots, fee_rate, portfolio_value, turnover_limit_value
    )
    return vb <= 1e-8 and vt <= 1e-8


def _repair_feasibility(
    x,
    unit,
    target_dollar,
    current_lots,
    fee_rate,
    portfolio_value,
    turnover_limit_value,
):
    x = x.copy()
    for _ in range(600):
        vb, vt = _violations(
            x, unit, current_lots, fee_rate, portfolio_value, turnover_limit_value
        )
        if vb <= 1e-8 and vt <= 1e-8:
            break

        base_v = vb + vt
        best_idx = None
        best_score = None
        base_obj = _objective(x, unit, target_dollar, current_lots, fee_rate)

        for i in range(x.size):
            if x[i] <= 0:
                continue
            x_try = x.copy()
            x_try[i] -= 1
            vb2, vt2 = _violations(
                x_try,
                unit,
                current_lots,
                fee_rate,
                portfolio_value,
                turnover_limit_value,
            )
            new_v = vb2 + vt2
            reduction = base_v - new_v
            if reduction <= 1e-12:
                continue
            obj_inc = _objective(x_try, unit, target_dollar, current_lots, fee_rate) - base_obj
            score = obj_inc / reduction
            if best_score is None or score < best_score:
                best_score = score
                best_idx = i

        if best_idx is None:
            break
        x[best_idx] -= 1

    return x


def solve_instance(instance: dict) -> dict:
    prices = np.asarray(instance["prices"], dtype=float)
    lot_sizes = np.asarray(instance["lot_sizes"], dtype=float)
    current_lots = np.asarray(instance["current_lots"], dtype=float)
    target_weights = np.asarray(instance["target_weights"], dtype=float)
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])
    turnover_limit_value = float(instance["turnover_limit_value"])
    max_lots = np.asarray(instance["max_lots"], dtype=float)

    unit = prices * lot_sizes
    target_dollar = target_weights * portfolio_value

    x_float = target_dollar / np.maximum(unit, 1e-12)
    x = np.rint(x_float)
    x = np.minimum(np.maximum(x, 0), max_lots)

    x = _repair_feasibility(
        x,
        unit,
        target_dollar,
        current_lots,
        fee_rate,
        portfolio_value,
        turnover_limit_value,
    )

    # Local search by +/-1 lot.
    for _ in range(200):
        improved = False
        base_obj = _objective(x, unit, target_dollar, current_lots, fee_rate)
        best_obj = base_obj
        best_x = x

        for i in range(x.size):
            for step in (-1, 1):
                xi = x[i] + step
                if xi < 0 or xi > max_lots[i]:
                    continue
                x_try = x.copy()
                x_try[i] = xi
                if not _is_feasible(
                    x_try,
                    unit,
                    current_lots,
                    fee_rate,
                    portfolio_value,
                    turnover_limit_value,
                ):
                    continue
                obj_try = _objective(x_try, unit, target_dollar, current_lots, fee_rate)
                if obj_try + 1e-10 < best_obj:
                    best_obj = obj_try
                    best_x = x_try

        if best_obj + 1e-10 < base_obj:
            x = best_x
            improved = True

        if not improved:
            break

    # Greedy fill for underweight assets if still feasible.
    for _ in range(150):
        holding = unit * x
        deficit = target_dollar - holding
        i = int(np.argmax(deficit))
        if deficit[i] <= 0:
            break
        if x[i] >= max_lots[i]:
            deficit[i] = -np.inf
            continue

        x_try = x.copy()
        x_try[i] += 1
        if _is_feasible(
            x_try,
            unit,
            current_lots,
            fee_rate,
            portfolio_value,
            turnover_limit_value,
        ):
            if _objective(x_try, unit, target_dollar, current_lots, fee_rate) < _objective(
                x, unit, target_dollar, current_lots, fee_rate
            ):
                x = x_try
                continue
        break

    x = np.rint(x).astype(int)
    return {"lots": x}
# EVOLVE-BLOCK-END
