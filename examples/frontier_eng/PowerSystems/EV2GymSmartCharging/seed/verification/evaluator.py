from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pkg_resources
import yaml


BENCHMARK_DIR = Path(__file__).resolve().parents[1]
REFERENCES_DIR = BENCHMARK_DIR / "references" / "upstream"
CONFIG_TEMPLATE_PATH = REFERENCES_DIR / "V2GProfitPlusLoads.yaml"
UPSTREAM_GITHUB_URL = "https://github.com/StavrosOrf/EV2Gym"

CASE_DEFINITIONS = [
    {
        "case_id": "workplace_winter_48cs_3tr",
        "seed": 17,
        "year": 2022,
        "month": 1,
        "day": 17,
        "hour": 5,
        "minute": 0,
        "number_of_charging_stations": 48,
        "number_of_transformers": 3,
        "baseline_cost": 180523.66220832747,
    },
    {
        "case_id": "workplace_spring_64cs_4tr",
        "seed": 29,
        "year": 2022,
        "month": 4,
        "day": 18,
        "hour": 5,
        "minute": 0,
        "number_of_charging_stations": 64,
        "number_of_transformers": 4,
        "baseline_cost": 288533.92933106923,
    },
    {
        "case_id": "workplace_autumn_96cs_5tr",
        "seed": 43,
        "year": 2022,
        "month": 10,
        "day": 10,
        "hour": 5,
        "minute": 0,
        "number_of_charging_stations": 96,
        "number_of_transformers": 5,
        "baseline_cost": 636962.0337206641,
    },
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _patch_upstream_resources() -> None:
    current = pkg_resources.resource_filename
    if getattr(current, "__name__", "") == "_frontier_ev2gym_resource_filename":
        return

    def _frontier_ev2gym_resource_filename(package: str, resource: str) -> str:
        if package == "ev2gym" and resource.startswith("data/"):
            local_path = REFERENCES_DIR / resource[len("data/") :]
            if local_path.exists():
                return str(local_path)
        return current(package, resource)

    pkg_resources.resource_filename = _frontier_ev2gym_resource_filename


def _load_candidate_module(candidate_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ev2gym_candidate", candidate_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load candidate module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_case_config(case_definition: dict[str, Any]) -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8"))
    config["random_day"] = False
    config["random_hour"] = False
    config["year"] = int(case_definition["year"])
    config["month"] = int(case_definition["month"])
    config["day"] = int(case_definition["day"])
    config["hour"] = int(case_definition["hour"])
    config["minute"] = int(case_definition["minute"])
    config["number_of_charging_stations"] = int(case_definition["number_of_charging_stations"])
    config["number_of_transformers"] = int(case_definition["number_of_transformers"])
    config["charging_network_topology"] = "None"
    config["ev_specs_file"] = str(REFERENCES_DIR / "ev_specs_v2g_enabled2024.json")
    return config


def _value_at_step(value: Any, step: int) -> float:
    array = np.asarray(value)
    if array.ndim == 0:
        return float(array.item())
    index = max(0, min(step, array.shape[0] - 1))
    return float(array[index])


def _transformer_snapshot(env: Any, step: int) -> list[dict[str, Any]]:
    transformers: list[dict[str, Any]] = []
    for transformer in env.transformers:
        transformers.append(
            {
                "transformer_id": int(transformer.id),
                "max_power_kw": _value_at_step(transformer.max_power, step),
                "min_power_kw": _value_at_step(transformer.min_power, step),
                "current_power_kw": _value_at_step(transformer.current_power, step),
                "is_overloaded": bool(transformer.is_overloaded()),
                "overload_kw": float(max(0.0, transformer.get_how_overloaded())),
                "inflexible_load_kw": _value_at_step(transformer.inflexible_load, step),
                "solar_power_kw": _value_at_step(transformer.solar_power, step),
                "charging_station_ids": [int(item) for item in transformer.cs_ids],
            }
        )
    return transformers


def _port_snapshot(env: Any, step: int) -> list[dict[str, Any]]:
    ports: list[dict[str, Any]] = []
    for charging_station in env.charging_stations:
        for port_index in range(charging_station.n_ports):
            ev = charging_station.evs_connected[port_index]
            snapshot = {
                "charging_station_id": int(charging_station.id),
                "port_index": int(port_index),
                "transformer_id": int(charging_station.connected_transformer),
                "connected": ev is not None,
                "charger_max_power_kw": float(charging_station.get_max_power()),
                "charger_min_charge_power_kw": float(charging_station.get_min_charge_power()),
                "charger_min_power_kw": float(charging_station.get_min_power()),
                "current_charge_price": float(env.charge_prices[charging_station.id, step]),
                "current_discharge_price": float(env.discharge_prices[charging_station.id, step]),
            }
            if ev is not None:
                snapshot.update(
                    {
                        "ev_id": int(ev.id),
                        "arrival_step": int(ev.time_of_arrival),
                        "departure_step": int(ev.time_of_departure),
                        "remaining_steps": max(0, int(ev.time_of_departure - step)),
                        "current_capacity_kwh": float(ev.current_capacity),
                        "desired_capacity_kwh": float(ev.desired_capacity),
                        "battery_capacity_kwh": float(ev.battery_capacity),
                        "min_battery_capacity_kwh": float(ev.min_battery_capacity),
                        "required_energy_kwh": float(ev.required_energy),
                        "max_ac_charge_power_kw": float(ev.max_ac_charge_power),
                        "max_dc_charge_power_kw": float(ev.max_dc_charge_power),
                        "max_discharge_power_kw": float(abs(ev.max_discharge_power)),
                        "charge_efficiency": _jsonable(ev.charge_efficiency),
                        "discharge_efficiency": _jsonable(ev.discharge_efficiency),
                    }
                )
            ports.append(snapshot)
    return ports


def _build_candidate_case(env: Any, case_definition: dict[str, Any]) -> dict[str, Any]:
    step = int(env.current_step)
    return {
        "case_id": str(case_definition["case_id"]),
        "current_step": step,
        "simulation_length": int(env.simulation_length),
        "remaining_steps": int(env.simulation_length - step),
        "timescale_minutes": float(env.timescale),
        "number_of_ports": int(env.number_of_ports),
        "number_of_charging_stations": int(env.cs),
        "number_of_transformers": int(env.number_of_transformers),
        "scenario": str(env.scenario),
        "v2g_enabled": bool(env.config["v2g_enabled"]),
        "current_power_usage_kw": float(env.current_power_usage[step]),
        "power_setpoint_kw": float(env.power_setpoints[step]),
        "future_charge_prices": [float(value) for value in env.charge_prices[0, step:].tolist()],
        "future_discharge_prices": [float(value) for value in env.discharge_prices[0, step:].tolist()],
        "transformers": _transformer_snapshot(env, step),
        "ports": _port_snapshot(env, step),
    }


def _coerce_actions(candidate_output: Any, number_of_ports: int) -> np.ndarray:
    raw_actions = candidate_output
    if isinstance(candidate_output, dict):
        if "actions" not in candidate_output:
            raise ValueError("candidate output dictionary must contain an 'actions' key")
        raw_actions = candidate_output["actions"]

    actions = np.asarray(raw_actions, dtype=float).reshape(-1)
    if actions.size != number_of_ports:
        raise ValueError(f"expected {number_of_ports} actions, received {actions.size}")
    if not np.all(np.isfinite(actions)):
        raise ValueError("actions must be finite numbers")
    if np.any(actions < -1.000001) or np.any(actions > 1.000001):
        raise ValueError("all actions must stay inside [-1, 1]")
    return np.clip(actions, -1.0, 1.0)


def _run_case(candidate_solve: Any, case_definition: dict[str, Any]) -> dict[str, Any]:
    _patch_upstream_resources()

    from ev2gym.models.ev2gym_env import EV2Gym
    from ev2gym.utilities.utils import get_statistics

    config = _build_case_config(case_definition)
    with tempfile.TemporaryDirectory(prefix="ev2gym_case_") as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        env = EV2Gym(
            config_file=str(config_path),
            seed=int(case_definition["seed"]),
            save_plots=False,
            save_replay=False,
            verbose=False,
        )
        env.reset(seed=int(case_definition["seed"]))

        done = False
        while not done:
            candidate_case = _build_candidate_case(env, case_definition)
            candidate_output = candidate_solve(candidate_case, max_sim_calls=0, simulate_fn=None)
            actions = _coerce_actions(candidate_output, env.number_of_ports)
            _, _, terminated, truncated, _ = env.step(actions)
            done = bool(terminated or truncated)

        stats = _jsonable(get_statistics(env))
        total_reward = float(stats["total_reward"])
        evaluation_cost = max(1e-9, -total_reward)
        normalized_score = 100.0 * float(case_definition["baseline_cost"]) / evaluation_cost

        return {
            "case_id": str(case_definition["case_id"]),
            "seed": int(case_definition["seed"]),
            "number_of_charging_stations": int(case_definition["number_of_charging_stations"]),
            "number_of_transformers": int(case_definition["number_of_transformers"]),
            "simulation_length": int(env.simulation_length),
            "num_spawned_evs": int(len(env.EVs)),
            "score_vs_official_baseline": float(normalized_score),
            "stats": stats,
        }


def evaluate_candidate(candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    candidate_module = _load_candidate_module(candidate_path)
    if not hasattr(candidate_module, "solve"):
        raise AttributeError("candidate module must define solve(case, max_sim_calls=0, simulate_fn=None)")

    case_results = [_run_case(candidate_module.solve, case_definition) for case_definition in CASE_DEFINITIONS]
    mean_total_reward = float(np.mean([result["stats"]["total_reward"] for result in case_results]))
    mean_total_profits = float(np.mean([result["stats"]["total_profits"] for result in case_results]))
    mean_energy_user_satisfaction = float(
        np.mean([result["stats"]["energy_user_satisfaction"] for result in case_results])
    )
    score = float(np.mean([result["score_vs_official_baseline"] for result in case_results]))

    return {
        "score": score,
        "valid": 1.0,
        "runtime_s": time.time() - started,
        "mean_total_reward": mean_total_reward,
        "mean_total_profits": mean_total_profits,
        "mean_energy_user_satisfaction": mean_energy_user_satisfaction,
        "source_repo": UPSTREAM_GITHUB_URL,
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an EV2Gym policy against fixed upstream-aligned cases.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--metrics-out", type=str, default=None)
    parser.add_argument("--artifacts-out", type=str, default=None)
    args = parser.parse_args()

    try:
        result = evaluate_candidate(args.candidate.resolve())
        metrics = {
            "combined_score": result["score"],
            "score": result["score"],
            "valid": result["valid"],
            "runtime_s": result["runtime_s"],
            "mean_total_reward": result["mean_total_reward"],
            "mean_total_profits": result["mean_total_profits"],
            "mean_energy_user_satisfaction": result["mean_energy_user_satisfaction"],
        }
        artifacts = {
            "source_repo": result["source_repo"],
            "cases": result["cases"],
        }
    except Exception as exc:
        runtime_s = 0.0
        metrics = {
            "combined_score": 0.0,
            "score": 0.0,
            "valid": 0.0,
            "runtime_s": runtime_s,
            "error": str(exc),
        }
        artifacts = {
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "source_repo": UPSTREAM_GITHUB_URL,
        }

    _write_json(args.metrics_out, metrics)
    _write_json(args.artifacts_out, artifacts)
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
