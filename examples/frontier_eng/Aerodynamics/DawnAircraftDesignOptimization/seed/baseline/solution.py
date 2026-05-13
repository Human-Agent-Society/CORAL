# EVOLVE-BLOCK-START
"""
DawnAircraftDesignOptimization baseline candidate.

DO NOT MODIFY:
- load_config()
- standard_atmosphere_density()
- evaluate_design()
- compute_constraint_margins()
- output format (submission.json)

ALLOWED TO MODIFY:
- solve_design()
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

DESIGN_KEYS = [
    "wing_span_m",
    "wing_area_m2",
    "fuselage_length_m",
    "fuselage_diameter_m",
    "motor_power_kw",
    "battery_mass_kg",
    "cruise_speed_mps",
]


def load_config() -> dict:
    """DO NOT MODIFY: load task configuration."""
    candidates = [
        Path("references/mission_config.json"),
        Path(__file__).resolve().parent.parent / "references" / "mission_config.json",
    ]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("mission_config.json not found")


def standard_atmosphere_density(altitude_m: float, constants: dict) -> float:
    """DO NOT MODIFY: simplified ISA density model (0-20 km)."""
    g = float(constants["gravity_mps2"])
    rho0 = float(constants["rho0_kgpm3"])
    t0 = float(constants["temperature0_k"])
    lapse = float(constants["lapse_rate_kpm"])
    r_air = float(constants["gas_constant_air"])

    h = float(max(0.0, altitude_m))
    if h <= 11000.0:
        t = t0 - lapse * h
        expn = g / (r_air * lapse) - 1.0
        rho = rho0 * (t / t0) ** expn
        return float(max(1e-5, rho))

    # Isothermal layer approximation above 11 km
    t11 = t0 - lapse * 11000.0
    expn = g / (r_air * lapse) - 1.0
    rho11 = rho0 * (t11 / t0) ** expn
    rho = rho11 * math.exp(-g * (h - 11000.0) / (r_air * t11))
    return float(max(1e-5, rho))


def _vector_to_design(x: np.ndarray) -> dict[str, float]:
    return {k: float(v) for k, v in zip(DESIGN_KEYS, x.tolist())}


def _design_to_vector(design: dict[str, float]) -> np.ndarray:
    return np.array([float(design[k]) for k in DESIGN_KEYS], dtype=float)


def _clip_design_to_bounds(design: dict[str, float], bounds: dict[str, list[float]]) -> dict[str, float]:
    clipped: dict[str, float] = {}
    for key in DESIGN_KEYS:
        lo, hi = bounds[key]
        clipped[key] = float(np.clip(float(design[key]), float(lo), float(hi)))
    return clipped


def evaluate_design(design: dict[str, float], cfg: dict) -> dict:
    """DO NOT MODIFY: physics, mass, and performance model."""
    mission = cfg["mission"]
    c = cfg["constants"]

    payload_kg = float(mission["payload_kg"])
    altitude_m = float(mission["cruise_altitude_m"])
    endurance_hr = float(mission["endurance_hr"])

    wing_span_m = float(design["wing_span_m"])
    wing_area_m2 = float(design["wing_area_m2"])
    fuselage_length_m = float(design["fuselage_length_m"])
    fuselage_diameter_m = float(design["fuselage_diameter_m"])
    motor_power_kw = float(design["motor_power_kw"])
    battery_mass_kg = float(design["battery_mass_kg"])
    cruise_speed_mps = float(design["cruise_speed_mps"])

    wing_mass_kg = (
        float(c["wing_mass_coeff"])
        * (wing_area_m2 ** 1.05)
        * ((wing_span_m / 20.0) ** 0.35)
    )
    fuselage_mass_kg = (
        float(c["fuselage_mass_coeff"])
        * fuselage_length_m
        * (fuselage_diameter_m ** 1.15)
    )
    tail_mass_kg = float(c["tail_mass_coeff"]) * (wing_area_m2 ** 0.55)
    landing_gear_mass_kg = float(c["landing_gear_mass_coeff"]) * math.sqrt(
        max(payload_kg + battery_mass_kg, 1e-6)
    )
    propulsion_mass_kg = (
        float(c["motor_mass_coeff"]) * (motor_power_kw ** 0.88)
        + float(c["propulsion_fixed_mass_kg"])
    )
    systems_mass_kg = float(c["systems_fixed_mass_kg"])

    total_mass_kg = (
        payload_kg
        + battery_mass_kg
        + wing_mass_kg
        + fuselage_mass_kg
        + tail_mass_kg
        + landing_gear_mass_kg
        + propulsion_mass_kg
        + systems_mass_kg
    )

    g = float(c["gravity_mps2"])
    rho0 = float(c["rho0_kgpm3"])
    rho_cruise = standard_atmosphere_density(altitude_m, c)
    weight_n = total_mass_kg * g

    aspect_ratio = wing_span_m ** 2 / max(wing_area_m2, 1e-6)
    mean_chord_m = wing_area_m2 / max(wing_span_m, 1e-6)

    q_cruise = 0.5 * rho_cruise * cruise_speed_mps ** 2
    cl_cruise = weight_n / max(q_cruise * wing_area_m2, 1e-6)

    cd0 = float(c["cd0_base"]) + float(c["cd0_fuselage_factor"]) * (
        fuselage_diameter_m / max(math.sqrt(wing_area_m2), 1e-6)
    )
    induced_factor = 1.0 / max(math.pi * float(c["oswald_efficiency"]) * aspect_ratio, 1e-6)
    cd_cruise = cd0 + induced_factor * cl_cruise ** 2

    drag_n = q_cruise * wing_area_m2 * cd_cruise
    cruise_power_required_w = (
        drag_n * cruise_speed_mps / max(float(c["eta_prop_cruise"]), 1e-6)
        + float(c["avionics_power_w"])
    )

    cl_max_takeoff = float(c["cl_max_takeoff"])
    stall_speed_mps = math.sqrt(2.0 * weight_n / max(rho0 * wing_area_m2 * cl_max_takeoff, 1e-6))
    v_to_mps = 1.2 * stall_speed_mps
    thrust_takeoff_n = (
        float(c["eta_prop_takeoff"]) * motor_power_kw * 1000.0 / max(v_to_mps, 5.0)
    )
    rolling_mu = float(c["rolling_friction_coeff"])
    accel_takeoff_mps2 = g * (thrust_takeoff_n / max(weight_n, 1e-6) - rolling_mu)
    takeoff_distance_m = (
        v_to_mps ** 2 / max(2.0 * accel_takeoff_mps2, 1e-6)
        if accel_takeoff_mps2 > 0.0
        else 1e12
    )

    load_factor = float(c["load_factor_limit"])
    root_bending_moment_nm = load_factor * weight_n * wing_span_m / 8.0
    spar_depth_m = float(c["thickness_to_chord"]) * mean_chord_m
    section_modulus_m3 = float(c["section_modulus_factor"]) * wing_area_m2 * spar_depth_m ** 2
    root_stress_pa = root_bending_moment_nm / max(section_modulus_m3, 1e-6)

    usable_energy_j = (
        battery_mass_kg
        * float(c["battery_specific_energy_wh_per_kg"])
        * 3600.0
        * float(c["usable_battery_fraction"])
        * float(c["battery_discharge_efficiency"])
    )
    required_energy_j = cruise_power_required_w * endurance_hr * 3600.0

    wing_loading_n_m2 = weight_n / max(wing_area_m2, 1e-6)

    return {
        "total_mass_kg": float(total_mass_kg),
        "wing_mass_kg": float(wing_mass_kg),
        "fuselage_mass_kg": float(fuselage_mass_kg),
        "tail_mass_kg": float(tail_mass_kg),
        "landing_gear_mass_kg": float(landing_gear_mass_kg),
        "propulsion_mass_kg": float(propulsion_mass_kg),
        "systems_mass_kg": float(systems_mass_kg),
        "weight_n": float(weight_n),
        "aspect_ratio": float(aspect_ratio),
        "mean_chord_m": float(mean_chord_m),
        "cl_cruise": float(cl_cruise),
        "cd_cruise": float(cd_cruise),
        "drag_n": float(drag_n),
        "cruise_power_required_w": float(cruise_power_required_w),
        "stall_speed_mps": float(stall_speed_mps),
        "takeoff_distance_m": float(takeoff_distance_m),
        "root_stress_pa": float(root_stress_pa),
        "usable_energy_j": float(usable_energy_j),
        "required_energy_j": float(required_energy_j),
        "wing_loading_n_m2": float(wing_loading_n_m2),
    }


def compute_constraint_margins(design: dict[str, float], result: dict, cfg: dict) -> dict[str, float]:
    """DO NOT MODIFY: unify all constraints as margins where >=0 is feasible."""
    cstr = cfg["constraints"]

    margins = {
        "aspect_ratio_min_margin": result["aspect_ratio"] - float(cstr["min_aspect_ratio"]),
        "aspect_ratio_max_margin": float(cstr["max_aspect_ratio"]) - result["aspect_ratio"],
        "fineness_margin": (
            design["fuselage_length_m"] / max(design["fuselage_diameter_m"], 1e-6)
            - float(cstr["min_fuselage_fineness"])
        ),
        "takeoff_distance_margin_m": float(cstr["max_takeoff_distance_m"]) - result["takeoff_distance_m"],
        "stall_speed_margin_mps": float(cstr["max_stall_speed_mps"]) - result["stall_speed_mps"],
        "lift_margin": float(cfg["constants"]["cl_max_cruise"]) - result["cl_cruise"],
        "stress_margin_pa": float(cstr["allowable_root_stress_pa"]) - result["root_stress_pa"],
        "energy_margin_j": result["usable_energy_j"] - result["required_energy_j"],
        "power_margin_w": (
            design["motor_power_kw"] * 1000.0 * float(cstr["required_power_headroom_fraction"])
            - result["cruise_power_required_w"]
        ),
        "wing_loading_margin_n_m2": float(cstr["max_wing_loading_n_m2"]) - result["wing_loading_n_m2"],
    }
    return {k: float(v) for k, v in margins.items()}


def _bounds_array(cfg: dict) -> list[tuple[float, float]]:
    bounds = cfg["bounds"]
    return [(float(bounds[k][0]), float(bounds[k][1])) for k in DESIGN_KEYS]


def _random_start(bounds: list[tuple[float, float]], rng: np.random.Generator) -> np.ndarray:
    vals = [rng.uniform(lo, hi) for lo, hi in bounds]
    return np.array(vals, dtype=float)


def _margin_scales(cfg: dict) -> dict[str, float]:
    cstr = cfg["constraints"]
    return {
        "aspect_ratio_min_margin": 2.0,
        "aspect_ratio_max_margin": 2.0,
        "fineness_margin": 1.0,
        "takeoff_distance_margin_m": 120.0,
        "stall_speed_margin_mps": 4.0,
        "lift_margin": 0.2,
        "stress_margin_pa": float(cstr["allowable_root_stress_pa"]),
        "energy_margin_j": 2e7,
        "power_margin_w": 3000.0,
        "wing_loading_margin_n_m2": 120.0,
    }


def _penalty_from_margins(margins: dict[str, float], scales: dict[str, float]) -> float:
    p = 0.0
    for name, val in margins.items():
        if val < 0.0:
            scale = max(1e-9, float(scales.get(name, 1.0)))
            p += (val / scale) ** 2
    return float(p)


def _evaluate_candidate(x: np.ndarray, cfg: dict, scales: dict[str, float]) -> tuple[dict, dict, float]:
    design = _vector_to_design(x)
    result = evaluate_design(design, cfg)
    margins = compute_constraint_margins(design, result, cfg)
    penalty = _penalty_from_margins(margins, scales)
    return result, margins, penalty


def _is_feasible(margins: dict[str, float]) -> bool:
    return all(v >= 0.0 and np.isfinite(v) for v in margins.values())


def _objective_with_penalty(x: np.ndarray, cfg: dict, scales: dict[str, float]) -> float:
    result, _, penalty = _evaluate_candidate(x, cfg, scales)
    return float(result["total_mass_kg"] + 2e4 * penalty)


def solve_design() -> dict[str, float]:
    """ALLOWED TO MODIFY: baseline solver (multi-start + finite-difference gradient + penalties)."""
    cfg = load_config()
    bounds = _bounds_array(cfg)
    scales = _margin_scales(cfg)

    x0 = _design_to_vector(cfg["baseline_initial_guess"])
    rng = np.random.default_rng(20260318)

    starts = [x0]
    for _ in range(7):
        starts.append(_random_start(bounds, rng))

    widths = np.array([hi - lo for lo, hi in bounds], dtype=float)

    def _project(x: np.ndarray) -> np.ndarray:
        y = x.copy()
        for i, (lo, hi) in enumerate(bounds):
            y[i] = float(np.clip(y[i], lo, hi))
        return y

    def _objective(x: np.ndarray) -> float:
        return _objective_with_penalty(x, cfg, scales)

    def _local_optimize(start: np.ndarray) -> np.ndarray:
        x = _project(start)
        best_obj = _objective(x)
        step = widths * 0.08

        for _ in range(140):
            improved = False

            # Coordinate pattern search (robust for non-smooth penalties).
            for i in range(len(x)):
                for sign in (-1.0, 1.0):
                    cand = x.copy()
                    cand[i] += sign * step[i]
                    cand = _project(cand)
                    obj = _objective(cand)
                    if obj < best_obj:
                        x = cand
                        best_obj = obj
                        improved = True

            # Finite-difference projected gradient step.
            grad = np.zeros_like(x)
            for i in range(len(x)):
                eps = max(1e-6, widths[i] * 1e-4)
                xp = x.copy()
                xm = x.copy()
                xp[i] += eps
                xm[i] -= eps
                xp = _project(xp)
                xm = _project(xm)
                fp = _objective(xp)
                fm = _objective(xm)
                grad[i] = (fp - fm) / max(1e-9, 2.0 * eps)

            grad_norm = float(np.linalg.norm(grad))
            if grad_norm > 0.0 and np.isfinite(grad_norm):
                grad /= grad_norm
                lr = float(np.mean(step))
                cand = _project(x - lr * grad)
                obj = _objective(cand)
                if obj < best_obj:
                    x = cand
                    best_obj = obj
                    improved = True

            if not improved:
                step *= 0.85
                if float(np.max(step)) < 1e-3:
                    break

        return x

    best_feasible_x: np.ndarray | None = None
    best_feasible_mass = float("inf")

    best_any_x: np.ndarray = x0.copy()
    best_any_obj = float("inf")

    for start in starts:
        x_try = _local_optimize(start)

        for i, (lo, hi) in enumerate(bounds):
            x_try[i] = float(np.clip(x_try[i], lo, hi))

        result, margins, penalty = _evaluate_candidate(x_try, cfg, scales)
        obj_val = float(result["total_mass_kg"] + 2e4 * penalty)

        if obj_val < best_any_obj:
            best_any_obj = obj_val
            best_any_x = x_try.copy()

        if _is_feasible(margins) and result["total_mass_kg"] < best_feasible_mass:
            best_feasible_mass = float(result["total_mass_kg"])
            best_feasible_x = x_try.copy()

    if best_feasible_x is None:
        # Fallback random search if local optimization misses feasibility.
        for _ in range(300):
            x_try = _random_start(bounds, rng)
            result, _, penalty = _evaluate_candidate(x_try, cfg, scales)
            obj_val = float(result["total_mass_kg"] + 2e4 * penalty)
            if obj_val < best_any_obj:
                best_any_obj = obj_val
                best_any_x = x_try.copy()
        x_final = best_any_x
    else:
        x_final = best_feasible_x

    design = _vector_to_design(x_final)
    design = _clip_design_to_bounds(design, cfg["bounds"])
    design["solver"] = "baseline_multistart_projected_gradient"
    return design


def main() -> None:
    design = solve_design()
    Path("submission.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cfg = load_config()
    metrics = evaluate_design(design, cfg)
    margins = compute_constraint_margins(design, metrics, cfg)
    feasible = _is_feasible(margins)

    print("submission.json generated")
    print(f"  total_mass_kg      : {metrics['total_mass_kg']:.3f}")
    print(f"  cruise_power_kw    : {metrics['cruise_power_required_w'] / 1000.0:.3f}")
    print(f"  takeoff_distance_m : {metrics['takeoff_distance_m']:.3f}")
    print(f"  feasible           : {feasible}")


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
