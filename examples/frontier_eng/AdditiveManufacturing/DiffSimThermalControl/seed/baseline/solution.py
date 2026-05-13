from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable

Simulator = Callable[[list[float], dict[str, Any]], dict[str, Any]]


def _softplus(value: float) -> float:
    if value > 30.0:
        return value
    if value < -30.0:
        return math.exp(value)
    return math.log1p(math.exp(value))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        exp_neg = math.exp(-value)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(value)
    return exp_pos / (1.0 + exp_pos)


# Keep this entrypoint stable: the evaluator loads real case lists through it.
# You may change case-construction details, but the returned fields must stay compatible.
def load_cases(case_file: str | Path | None = None) -> list[dict[str, Any]]:
    if case_file is None:
        case_file = Path(__file__).resolve().parent.parent / "references" / "cases.json"
    root = Path(case_file).expanduser().resolve()
    meta = json.loads(root.read_text(encoding="utf-8"))
    original_dir = root.parent / "original"
    toolpath_samples = _resample_toolpath(original_dir / "toolpath.crs", dt=float(meta["constants"]["dt"]))
    constants = dict(meta["constants"])
    cases = []
    for case_meta in meta["cases"]:
        cases.append(_build_case(case_meta, toolpath_samples, constants))
    return cases


def _resample_toolpath(path: Path, dt: float) -> list[dict[str, float]]:
    raw: list[tuple[float, float, float, float, int]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if not parts:
                continue
            t, x, y, z, state = parts
            raw.append((float(t), float(x), float(y), float(z), int(float(state))))

    samples: list[dict[str, float]] = []
    ctime = 0.0
    index = 0
    end_time = raw[-1][0]
    while ctime <= end_time:
        while index + 1 < len(raw) - 1 and ctime >= raw[index + 1][0]:
            index += 1
        t0, x0, y0, z0, _ = raw[index]
        t1, x1, y1, z1, s1 = raw[index + 1]
        ratio = 0.0 if t1 <= t0 else (ctime - t0) / (t1 - t0)
        sample = {
            "time": ctime,
            "x": x0 + (x1 - x0) * ratio,
            "y": y0 + (y1 - y0) * ratio,
            "z": z0 + (z1 - z0) * ratio,
            "state": float(s1),
        }
        samples.append(sample)
        ctime += dt
    return samples


def _build_case(case_meta: dict[str, Any], samples: list[dict[str, float]], constants: dict[str, Any]) -> dict[str, Any]:
    layer = int(case_meta["layer"])
    dt = float(constants["dt"])
    layer_samples = [sample for sample in samples if round(sample["z"]) == layer and sample["state"] > 0.5]
    if not layer_samples:
        raise ValueError(f"no samples found for layer {layer}")

    cooldown_steps = int(float(case_meta.get("cooldown_s", 1.0)) / dt)
    last = layer_samples[-1]
    for offset in range(cooldown_steps):
        layer_samples.append(
            {
                "time": last["time"] + dt * (offset + 1),
                "x": last["x"],
                "y": last["y"],
                "z": last["z"],
                "state": 0.0,
            }
        )

    speeds = [0.0]
    turn_norm = [0.0 for _ in layer_samples]
    for index in range(1, len(layer_samples)):
        prev = layer_samples[index - 1]
        curr = layer_samples[index]
        speeds.append(math.dist((prev["x"], prev["y"], prev["z"]), (curr["x"], curr["y"], curr["z"])) / dt)
    for index in range(1, len(layer_samples) - 1):
        prev = layer_samples[index - 1]
        curr = layer_samples[index]
        nxt = layer_samples[index + 1]
        v1 = (curr["x"] - prev["x"], curr["y"] - prev["y"])
        v2 = (nxt["x"] - curr["x"], nxt["y"] - curr["y"])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 * n2 > 1e-9:
            cosine = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
            turn_norm[index] = math.acos(cosine) / math.pi

    speed_mean = sum(speeds) / len(speeds)
    target_mid = 0.5 * (float(constants["solidus"]) + float(constants["liquidus"]))
    target_profile: list[float] = []
    for speed_value, turn_value, sample in zip(speeds, turn_norm, layer_samples):
        speed_dev = speed_value - speed_mean
        target_temp = target_mid - 40.0 * turn_value + 6.0 * speed_dev + 8.0 * sample["state"]
        target_profile.append(target_temp)

    return {
        "case_id": case_meta["case_id"],
        "layer": layer,
        "dt": dt,
        "times": [sample["time"] for sample in layer_samples],
        "positions": [[sample["x"], sample["y"], sample["z"]] for sample in layer_samples],
        "laser_state": [sample["state"] for sample in layer_samples],
        "speed": speeds,
        "turn": turn_norm,
        "target_profile": target_profile,
        **constants,
    }


def _interpolation_weights(num_steps: int, num_knots: int) -> list[list[tuple[int, float]]]:
    if num_knots < 2:
        raise ValueError("num_knots must be >= 2")
    weights: list[list[tuple[int, float]]] = []
    if num_steps == 1:
        return [[(0, 1.0)]]
    for step in range(num_steps):
        location = step * (num_knots - 1) / (num_steps - 1)
        left = int(math.floor(location))
        right = min(left + 1, num_knots - 1)
        frac = location - left
        if right == left:
            weights.append([(left, 1.0)])
        else:
            weights.append([(left, 1.0 - frac), (right, frac)])
    return weights


def _expand_controls(knots: list[float], weights: list[list[tuple[int, float]]]) -> list[float]:
    powers: list[float] = []
    for step_weights in weights:
        value = 0.0
        for knot_index, coeff in step_weights:
            value += coeff * knots[knot_index]
        powers.append(value)
    return powers


# Keep this function available: it projects candidate control knots into the feasible set.
# You may change the projection strategy, clipping order, and ramp handling details.
def project_params(params: list[float], case: dict[str, Any]) -> list[float]:
    ramp_limit = float(case["ramp_limit"])
    projected: list[float] = []
    for index, raw in enumerate(params):
        value = min(max(float(raw), 0.0), 1.0)
        if index > 0:
            prev = projected[-1]
            value = min(max(value, prev - ramp_limit), prev + ramp_limit)
        projected.append(value)
    return projected


# Keep this interface stable: the evaluator calls `simulate(params, case)` directly.
# You may change the thermal surrogate model, loss terms, and numerical details.
def simulate(params: list[float], case: dict[str, Any]) -> dict[str, Any]:
    control_knots = int(case["control_knots"])
    knots = [float(value) for value in params]
    if len(knots) != control_knots:
        return {
            "loss": float("inf"),
            "feasible": False,
            "constraint_violation": float("inf"),
            "error": f"expected {control_knots} params, got {len(knots)}",
        }

    projected = project_params(knots, case)
    bound_violation = sum(abs(a - b) for a, b in zip(knots, projected))
    feasible = bound_violation <= 1e-9

    weights = _interpolation_weights(len(case["target_profile"]), control_knots)
    powers = _expand_controls(projected, weights)
    temperatures = _temperature_rollout(powers, case)

    track = 0.0
    under = 0.0
    over = 0.0
    smooth = 0.0
    energy = 0.0
    for index, temperature in enumerate(temperatures):
        target = float(case["target_profile"][index])
        track += ((temperature - target) / 80.0) ** 2
        under += _softplus((float(case["solidus"]) - temperature) / 25.0) ** 2
        over += _softplus((temperature - float(case["liquidus"])) / 25.0) ** 2
        energy += (powers[index] - float(case["nominal_power"])) ** 2
        if index > 0:
            smooth += ((powers[index] - powers[index - 1]) / float(case["ramp_limit"])) ** 2
    steps = float(len(temperatures))
    loss = 1.0 * track / steps + 0.8 * under / steps + 1.2 * over / steps + 0.08 * energy / steps + 0.04 * smooth / max(steps - 1.0, 1.0)
    loss += 20.0 * bound_violation

    return {
        "loss": loss,
        "feasible": feasible,
        "constraint_violation": bound_violation,
        "powers": powers,
        "temperatures": temperatures,
        "mean_temperature": sum(temperatures) / steps,
        "max_temperature": max(temperatures),
    }


def _temperature_rollout(powers: list[float], case: dict[str, Any]) -> list[float]:
    temperature = float(case["ambient"])
    temperatures: list[float] = []
    memory = float(case["memory"])
    q_in = float(case["q_in"])
    heat_gain = float(case["heat_gain"])
    speed_weight = float(case["speed_weight"])
    turn_weight = float(case["turn_weight"])
    max_temp = float(case["max_temp"])
    for power, active, speed, turn in zip(powers, case["laser_state"], case["speed"], case["turn"]):
        local_heat = heat_gain * q_in * power * active * (1.0 + turn_weight * turn) / (1.0 + speed_weight * speed)
        temperature = float(case["ambient"]) + memory * (temperature - float(case["ambient"])) + local_heat
        temperature = min(max_temp, temperature)
        temperatures.append(temperature)
    return temperatures


def _loss_gradient(params: list[float], case: dict[str, Any]) -> list[float]:
    knots = project_params([float(value) for value in params], case)
    control_knots = int(case["control_knots"])
    weights = _interpolation_weights(len(case["target_profile"]), control_knots)
    powers = _expand_controls(knots, weights)
    temperatures = _temperature_rollout(powers, case)

    steps = len(temperatures)
    dloss_dtemp = [0.0 for _ in range(steps)]
    dloss_dpower = [0.0 for _ in range(steps)]
    for index, temperature in enumerate(temperatures):
        target = float(case["target_profile"][index])
        dloss_dtemp[index] += 2.0 * (temperature - target) / (80.0 * 80.0 * steps)
        under_raw = (float(case["solidus"]) - temperature) / 25.0
        under_sp = _softplus(under_raw)
        dloss_dtemp[index] += -2.0 * 0.8 * under_sp * _sigmoid(under_raw) / (25.0 * steps)
        over_raw = (temperature - float(case["liquidus"])) / 25.0
        over_sp = _softplus(over_raw)
        dloss_dtemp[index] += 2.0 * 1.2 * over_sp * _sigmoid(over_raw) / (25.0 * steps)
        dloss_dpower[index] += 2.0 * 0.08 * (powers[index] - float(case["nominal_power"])) / steps
        if index > 0:
            coeff = 2.0 * 0.04 * (powers[index] - powers[index - 1]) / (float(case["ramp_limit"]) ** 2 * max(steps - 1, 1))
            dloss_dpower[index] += coeff
            dloss_dpower[index - 1] -= coeff

    memory = float(case["memory"])
    q_in = float(case["q_in"])
    heat_gain = float(case["heat_gain"])
    speed_weight = float(case["speed_weight"])
    turn_weight = float(case["turn_weight"])
    adjoint = 0.0
    for index in range(steps - 1, -1, -1):
        local_coeff = heat_gain * q_in * float(case["laser_state"][index]) * (1.0 + turn_weight * float(case["turn"][index])) / (1.0 + speed_weight * float(case["speed"][index]))
        adjoint += dloss_dtemp[index]
        dloss_dpower[index] += adjoint * local_coeff
        adjoint *= memory

    knot_grad = [0.0 for _ in range(control_knots)]
    for step_index, step_weights in enumerate(weights):
        for knot_index, coeff in step_weights:
            knot_grad[knot_index] += dloss_dpower[step_index] * coeff
    return knot_grad


def _adam_optimize(case: dict[str, Any], *, max_sim_calls: int, simulate_fn: Simulator, step_size: float, beta1: float = 0.9, beta2: float = 0.999) -> dict[str, Any]:
    control_knots = int(case["control_knots"])
    params = [float(case["nominal_power"]) for _ in range(control_knots)]
    m = [0.0 for _ in range(control_knots)]
    v = [0.0 for _ in range(control_knots)]
    best = simulate_fn(params, case)
    best_params = params[:]
    history = [float(best["loss"])]
    sim_calls = 1
    iteration = 0
    while sim_calls < max_sim_calls:
        iteration += 1
        grad = _loss_gradient(params, case)
        for i in range(control_knots):
            m[i] = beta1 * m[i] + (1.0 - beta1) * grad[i]
            v[i] = beta2 * v[i] + (1.0 - beta2) * grad[i] * grad[i]
            m_hat = m[i] / (1.0 - beta1 ** iteration)
            v_hat = v[i] / (1.0 - beta2 ** iteration)
            params[i] -= step_size * m_hat / (math.sqrt(v_hat) + 1e-8)
        params = project_params(params, case)
        metrics = simulate_fn(params, case)
        sim_calls += 1
        if metrics["loss"] <= best["loss"]:
            best = metrics
            best_params = params[:]
        history.append(float(best["loss"]))
    return {
        "params": best_params,
        "best_loss": float(best["loss"]),
        "sim_calls": sim_calls,
        "history": history,
    }


# Keep this baseline interface stable for producing reference results.
# You may change the default hyperparameters and optimizer choice.
def baseline_solve(case: dict[str, Any], max_sim_calls: int = 24, simulate_fn: Simulator | None = None) -> dict[str, Any]:
    simulator = simulate if simulate_fn is None else simulate_fn
    return _adam_optimize(case, max_sim_calls=max_sim_calls, simulate_fn=simulator, step_size=0.06)


# Keep this unified evaluation entrypoint stable.
# You may change the optimization loop, initialization, step-size schedule, and projection handling.
def solve(case: dict[str, Any], max_sim_calls: int = 24, simulate_fn: Simulator | None = None) -> dict[str, Any]:
    simulator = simulate if simulate_fn is None else simulate_fn
    return _adam_optimize(case, max_sim_calls=max_sim_calls, simulate_fn=simulator, step_size=0.06)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference optimizer for the real additive-manufacturing toolpath case")
    parser.add_argument("--case-file", type=str, default=None)
    parser.add_argument("--case-id", type=str, default=None)
    parser.add_argument("--max-sim-calls", type=int, default=24)
    parser.add_argument("--output", type=str, default="submission.json")
    args = parser.parse_args()

    cases = load_cases(args.case_file)
    case = cases[0]
    if args.case_id is not None:
        matches = [item for item in cases if item["case_id"] == args.case_id]
        if not matches:
            raise SystemExit(f"unknown case_id: {args.case_id}")
        case = matches[0]

    result = solve(case, max_sim_calls=args.max_sim_calls)
    metrics = simulate(result["params"], case)
    payload = {
        "case_id": case["case_id"],
        "params": result["params"],
        "best_loss": metrics["loss"],
        "sim_calls": result["sim_calls"],
        "mean_temperature": metrics["mean_temperature"],
        "max_temperature": metrics["max_temperature"],
    }
    _write_json(Path(args.output).expanduser().resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
