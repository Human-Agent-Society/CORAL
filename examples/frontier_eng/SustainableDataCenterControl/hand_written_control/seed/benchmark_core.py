from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np

BENCHMARK_ROOT = Path(__file__).resolve().parent
DEFAULT_SUSTAINDC_ROOT = BENCHMARK_ROOT / "sustaindc"
SUSTAINDC_ROOT_ENV = "SUSTAINDC_ROOT"


TIMESTEPS_PER_DAY = 96
AGENT_NAMES = ("agent_ls", "agent_dc", "agent_bat")

ACTION_DESCRIPTIONS = {
    "agent_ls": {
        0: "Defer flexible jobs into the queue.",
        1: "Keep the queue unchanged.",
        2: "Execute jobs from the queue.",
    },
    "agent_dc": {
        0: "Decrease the cooling setpoint (more cooling).",
        1: "Keep the cooling setpoint unchanged.",
        2: "Increase the cooling setpoint (less cooling).",
    },
    "agent_bat": {
        0: "Charge the battery.",
        1: "Discharge the battery.",
        2: "Keep the battery idle.",
    },
}

LS_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "queue_oldest_task_age_norm",
    "queue_average_task_age_norm",
    "queue_fill_ratio",
    "workload_current",
    "outdoor_temp_current_norm",
    "temp_future_slope",
    "temp_future_mean",
    "temp_future_std",
    "temp_percentile",
    "temp_time_to_next_peak_norm",
    "temp_time_to_next_valley_norm",
    "queue_hist_0_6h",
    "queue_hist_6_12h",
    "queue_hist_12_18h",
    "queue_hist_18_24h",
    "queue_hist_over_24h",
]

DC_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "workload_current",
    "workload_next",
    "outdoor_temp_current_norm",
    "outdoor_temp_next_norm",
]

BAT_FEATURES = [
    "time_cos_hour",
    "time_sin_hour",
    "ci_current_norm",
    "ci_future_slope",
    "ci_past_slope",
    "ci_future_mean",
    "ci_future_std",
    "ci_percentile",
    "ci_time_to_next_peak_norm",
    "ci_time_to_next_valley_norm",
    "workload_current",
    "outdoor_temp_current_norm",
    "battery_soc",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    location: str
    month: int
    days_per_episode: int
    seed: int
    description: str


@dataclass
class EpisodeMetrics:
    scenario: str
    steps: int = 0
    carbon_kg: float = 0.0
    water_l: float = 0.0
    dropped_tasks: float = 0.0
    overdue_tasks: float = 0.0
    grid_energy_kwh: float = 0.0
    avg_soc: float = 0.0
    total_reward: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["avg_soc"] = float(self.avg_soc)
        return data


SCENARIOS = [
    Scenario(
        name="az_july",
        location="az",
        month=6,
        days_per_episode=2,
        seed=11,
        description="Arizona summer: hot weather with expensive cooling decisions.",
    ),
    Scenario(
        name="ca_april",
        location="ca",
        month=3,
        days_per_episode=2,
        seed=17,
        description="California spring: milder weather, still non-trivial carbon scheduling.",
    ),
    Scenario(
        name="ny_january",
        location="ny",
        month=0,
        days_per_episode=2,
        seed=23,
        description="New York winter: lower outdoor temperatures and different demand profile.",
    ),
    Scenario(
        name="tx_august",
        location="tx",
        month=7,
        days_per_episode=2,
        seed=29,
        description="Texas late summer: high thermal pressure and volatile carbon intensity.",
    ),
]


BENCHMARK_ENV_CONFIG = {
    "agents": list(AGENT_NAMES),
    "workload_file": "Alibaba_CPU_Data_Hourly_1.csv",
    "max_bat_cap_Mw": 1.0,
    "individual_reward_weight": 0.8,
    "flexible_load": 0.6,
    "dc_config_file": "dc_config.json",
    "evaluation": False,
}


class NoOpPolicy:
    @staticmethod
    def reset_policy() -> None:
        return None

    @staticmethod
    def decide_actions(observations: Mapping[str, np.ndarray]) -> Dict[str, int]:
        return {
            "agent_ls": 1,
            "agent_dc": 1,
            "agent_bat": 2,
        }


def resolve_sustaindc_root(explicit_root: str | Path | None = None) -> Path:
    candidate = explicit_root or os.environ.get(SUSTAINDC_ROOT_ENV, DEFAULT_SUSTAINDC_ROOT)
    root = Path(candidate).expanduser().resolve()
    if not (root / "sustaindc_env.py").exists():
        raise FileNotFoundError(
            "Could not find a SustainDC checkout. Expected "
            f"{root / 'sustaindc_env.py'}. Clone dc-rl into the sibling "
            f"directory or pass --sustaindc-root /path/to/dc-rl."
        )
    return root


def _clear_cached_utils_if_needed(sustaindc_root: Path) -> None:
    cached_utils = sys.modules.get("utils")
    expected_utils = sustaindc_root / "utils" / "__init__.py"
    cached_utils_file = Path(getattr(cached_utils, "__file__", "")).resolve() if cached_utils else None
    if cached_utils is not None and cached_utils_file != expected_utils:
        for module_name in list(sys.modules):
            if module_name == "utils" or module_name.startswith("utils."):
                sys.modules.pop(module_name, None)


def _load_sustaindc_modules(sustaindc_root: str | Path | None = None):
    root = resolve_sustaindc_root(sustaindc_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _clear_cached_utils_if_needed(root)
    cached_env_module = sys.modules.get("sustaindc_env")
    expected_env_file = root / "sustaindc_env.py"
    cached_env_file = (
        Path(getattr(cached_env_module, "__file__", "")).resolve()
        if cached_env_module is not None
        else None
    )
    if cached_env_module is not None and cached_env_file != expected_env_file:
        sys.modules.pop("sustaindc_env", None)

    env_module = importlib.import_module("sustaindc_env")
    utils_module = importlib.import_module("utils.utils_cf")
    return root, env_module, env_module.SustainDC, utils_module.get_init_day


def load_policy_module(solution_path: Path):
    spec = importlib.util.spec_from_file_location("benchmark_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load solution module from {solution_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "decide_actions"):
        raise AttributeError(
            f"{solution_path} must define a decide_actions(observations) function."
        )
    return module


def _build_env(scenario: Scenario, sustaindc_root: str | Path | None = None):
    _, env_module, SustainDC, get_init_day = _load_sustaindc_modules(sustaindc_root)
    env_config = dict(BENCHMARK_ENV_CONFIG)
    env_config.update(
        {
            "location": scenario.location,
            "month": scenario.month,
            "days_per_episode": scenario.days_per_episode,
        }
    )
    env_defaults = getattr(getattr(env_module, "EnvConfig", None), "DEFAULT_CONFIG", {})
    if "fixed_init_day" in env_defaults and "fixed_init_hour" in env_defaults:
        env_config.update(
            {
                "fixed_init_day": get_init_day(scenario.month) + 3,
                "fixed_init_hour": 12,
            }
        )
    return SustainDC(env_config)


def _reset_policy_if_available(policy_module: Any) -> None:
    if hasattr(policy_module, "reset_policy"):
        policy_module.reset_policy()


def _coerce_actions(actions: Mapping[str, Any]) -> Dict[str, int]:
    missing = [agent for agent in AGENT_NAMES if agent not in actions]
    if missing:
        raise KeyError(f"Policy output is missing actions for: {missing}")

    coerced: Dict[str, int] = {}
    for agent in AGENT_NAMES:
        action = int(actions[agent])
        if action not in ACTION_DESCRIPTIONS[agent]:
            raise ValueError(
                f"{agent} produced invalid action {action}. "
                f"Valid actions are {sorted(ACTION_DESCRIPTIONS[agent])}."
            )
        coerced[agent] = action
    return coerced


def _close_env(env: Any) -> None:
    try:
        env.close()
    except Exception:
        pass

    for sub_env_name in ("ls_env", "dc_env", "bat_env"):
        sub_env = getattr(env, sub_env_name, None)
        if sub_env is not None and hasattr(sub_env, "close"):
            try:
                sub_env.close()
            except Exception:
                pass


def run_episode(
    policy_module: Any,
    scenario: Scenario,
    sustaindc_root: str | Path | None = None,
) -> EpisodeMetrics:
    random.seed(scenario.seed)
    np.random.seed(scenario.seed)
    env = _build_env(scenario, sustaindc_root=sustaindc_root)
    try:
        env.seed(scenario.seed)
        _reset_policy_if_available(policy_module)
        observations = env.reset()

        metrics = EpisodeMetrics(scenario=scenario.name)
        soc_trace = []

        while True:
            actions = _coerce_actions(policy_module.decide_actions(observations))
            observations, rewards, terminateds, truncateds, infos = env.step(actions)
            common = infos["__common__"]

            metrics.steps += 1
            metrics.carbon_kg += float(common["bat_CO2_footprint"]) / 1000.0
            metrics.water_l += float(common["dc_water_usage"])
            metrics.dropped_tasks += float(common["ls_tasks_dropped"])
            metrics.overdue_tasks += float(common["ls_overdue_penalty"])
            metrics.grid_energy_kwh += float(common["bat_total_energy_with_battery_KWh"])
            metrics.total_reward += sum(float(v) for v in rewards.values())
            soc_trace.append(float(common["bat_SOC"]))

            if terminateds.get("__all__") or truncateds.get("__all__"):
                break

        if soc_trace:
            metrics.avg_soc = float(np.mean(soc_trace))
        return metrics
    finally:
        _close_env(env)


def _metric_improvement(candidate: float, reference: float, floor: float) -> float:
    denom = max(reference, floor)
    raw_gain = 1.0 - candidate / denom
    if raw_gain <= NOISE_TOLERANCE:
        return 0.0
    return float(np.clip(raw_gain, 0.0, 1.0))


def score_episode(candidate: EpisodeMetrics, reference: EpisodeMetrics) -> Dict[str, float]:
    carbon_gain = _metric_improvement(candidate.carbon_kg, reference.carbon_kg, 1e-9)
    water_gain = _metric_improvement(candidate.water_l, reference.water_l, 1e-9)
    improvement_fraction = 0.85 * carbon_gain + 0.15 * water_gain
    base_score = 100.0 * np.sqrt(improvement_fraction)
    safety_penalty = 5.0 * candidate.dropped_tasks + 0.5 * candidate.overdue_tasks
    final_score = float(np.clip(base_score - safety_penalty, 0.0, 100.0))

    return {
        "carbon_gain": round(carbon_gain, 6),
        "water_gain": round(water_gain, 6),
        "improvement_fraction": round(float(improvement_fraction), 6),
        "base_score": round(float(base_score), 4),
        "safety_penalty": round(float(safety_penalty), 4),
        "score": round(final_score, 4),
        "theoretical_ceiling": 100.0,
    }


def aggregate_metrics(metrics: list[EpisodeMetrics]) -> Dict[str, float]:
    return {
        "steps": int(sum(item.steps for item in metrics)),
        "carbon_kg": float(sum(item.carbon_kg for item in metrics)),
        "water_l": float(sum(item.water_l for item in metrics)),
        "dropped_tasks": float(sum(item.dropped_tasks for item in metrics)),
        "overdue_tasks": float(sum(item.overdue_tasks for item in metrics)),
        "grid_energy_kwh": float(sum(item.grid_energy_kwh for item in metrics)),
        "avg_soc": float(np.mean([item.avg_soc for item in metrics])),
        "total_reward": float(sum(item.total_reward for item in metrics)),
    }


def run_benchmark(
    policy_module: Any,
    sustaindc_root: str | Path | None = None,
) -> Dict[str, Any]:
    candidate_results: list[EpisodeMetrics] = []
    noop_results: list[EpisodeMetrics] = []
    scenario_reports: list[Dict[str, Any]] = []
    resolved_root = resolve_sustaindc_root(sustaindc_root)

    for scenario in SCENARIOS:
        candidate_metrics = run_episode(
            policy_module,
            scenario,
            sustaindc_root=resolved_root,
        )
        noop_metrics = run_episode(
            NoOpPolicy,
            scenario,
            sustaindc_root=resolved_root,
        )
        score_breakdown = score_episode(candidate_metrics, noop_metrics)

        candidate_results.append(candidate_metrics)
        noop_results.append(noop_metrics)
        scenario_reports.append(
            {
                "scenario": asdict(scenario),
                "candidate": candidate_metrics.as_dict(),
                "noop_reference": noop_metrics.as_dict(),
                "score_breakdown": score_breakdown,
            }
        )

    average_score = float(
        np.mean([report["score_breakdown"]["score"] for report in scenario_reports])
    )

    return {
        "average_score": round(average_score, 4),
        "score_ceiling": 100.0,
        "sustaindc_root": str(resolved_root),
        "scenario_reports": scenario_reports,
        "candidate_aggregate": aggregate_metrics(candidate_results),
        "noop_aggregate": aggregate_metrics(noop_results),
        "feature_reference": {
            "agent_ls": LS_FEATURES,
            "agent_dc": DC_FEATURES,
            "agent_bat": BAT_FEATURES,
        },
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        "Function Benchmark Evaluation",
        f"Average score: {report['average_score']:.2f} / {report['score_ceiling']:.2f}",
        "",
    ]

    for scenario_report in report["scenario_reports"]:
        scenario = scenario_report["scenario"]
        score = scenario_report["score_breakdown"]["score"]
        candidate = scenario_report["candidate"]
        noop = scenario_report["noop_reference"]
        lines.extend(
            [
                f"[{scenario['name']}] {scenario['description']}",
                f"  score: {score:.2f} / 100.00",
                (
                    "  candidate metrics: "
                    f"carbon={candidate['carbon_kg']:.2f}kg, "
                    f"water={candidate['water_l']:.2f}L, "
                    f"dropped={candidate['dropped_tasks']:.0f}, "
                    f"overdue={candidate['overdue_tasks']:.0f}"
                ),
                (
                    "  noop metrics:      "
                    f"carbon={noop['carbon_kg']:.2f}kg, "
                    f"water={noop['water_l']:.2f}L, "
                    f"dropped={noop['dropped_tasks']:.0f}, "
                    f"overdue={noop['overdue_tasks']:.0f}"
                ),
                "",
            ]
        )

    candidate_aggregate = report["candidate_aggregate"]
    lines.extend(
        [
            "Aggregate candidate metrics",
            json.dumps(candidate_aggregate, indent=2),
            "",
            "Aggregate noop reference metrics",
            json.dumps(report["noop_aggregate"], indent=2),
        ]
    )
    return "\n".join(lines)
NOISE_TOLERANCE = 0.002
