#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any


TASK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = TASK_ROOT / "references" / "battery_config.json"
FARADAY_C_PER_MOL = 96485.33212
GAS_CONSTANT_J_PER_MOLK = 8.314462618


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("battery config must be a JSON object")
    return data


def _arrhenius_scale(temp_k: float, temp_ref_k: float, activation_energy: float) -> float:
    return math.exp((activation_energy / GAS_CONSTANT_J_PER_MOLK) * (1.0 / temp_ref_k - 1.0 / temp_k))


def _theta_n_from_soc(soc: float, cfg: dict[str, Any]) -> float:
    battery = cfg["battery"]
    return float(battery["theta_n_min"]) + soc * (float(battery["theta_n_max"]) - float(battery["theta_n_min"]))


def _theta_p_from_soc(soc: float, cfg: dict[str, Any]) -> float:
    battery = cfg["battery"]
    return float(battery["theta_p_max"]) - soc * (float(battery["theta_p_max"]) - float(battery["theta_p_min"]))


def _soc_from_theta_n(theta_n: float, cfg: dict[str, Any]) -> float:
    battery = cfg["battery"]
    return (theta_n - float(battery["theta_n_min"])) / (
        float(battery["theta_n_max"]) - float(battery["theta_n_min"])
    )


def _ocv_positive(theta_p: float, temp_k: float, cfg: dict[str, Any]) -> float:
    model = cfg["ocv_positive"]
    z = _clamp(theta_p, 1e-6, 1.0 - 1e-6)
    temp_ref_k = float(cfg["simulation"]["temperature_ref_k"])
    return (
        float(model["base_v"])
        + float(model["linear_coeff"]) * z
        + float(model["plateau_amp_1_v"]) * math.tanh((z - float(model["plateau_center_1"])) * float(model["plateau_gain_1"]))
        + float(model["plateau_amp_2_v"]) * math.tanh((z - float(model["plateau_center_2"])) * float(model["plateau_gain_2"]))
        + float(model["temp_coeff_v_per_k"]) * (temp_k - temp_ref_k)
    )


def _ocv_negative(theta_n: float, temp_k: float, cfg: dict[str, Any]) -> float:
    model = cfg["ocv_negative"]
    z = _clamp(theta_n, 1e-6, 1.0 - 1e-6)
    temp_ref_k = float(cfg["simulation"]["temperature_ref_k"])
    return (
        float(model["base_v"])
        + float(model["linear_coeff"]) * z
        + float(model["plateau_amp_1_v"]) * math.tanh((z - float(model["plateau_center_1"])) * float(model["plateau_gain_1"]))
        + float(model["plateau_amp_2_v"]) * math.tanh((z - float(model["plateau_center_2"])) * float(model["plateau_gain_2"]))
        + float(model["temp_coeff_v_per_k"]) * (temp_k - temp_ref_k)
    )


def _entropy_term(theta_p: float, theta_n: float, cfg: dict[str, Any]) -> float:
    thermal = cfg["thermal"]
    return (
        float(thermal["entropy_coeff_p_v_per_k"]) * (theta_p - 0.5)
        - float(thermal["entropy_coeff_n_v_per_k"]) * (theta_n - 0.5)
    )


def _load_candidate(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("battery_fast_charge_spme_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load candidate module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "build_charging_policy"):
        raise AttributeError("candidate must define build_charging_policy()")
    fn = getattr(module, "build_charging_policy")
    if not callable(fn):
        raise TypeError("build_charging_policy must be callable")
    return fn()


def _validate_policy(policy: Any, cfg: dict[str, Any]) -> tuple[list[float], list[float]]:
    if not isinstance(policy, dict):
        raise TypeError("build_charging_policy() must return a dict")

    currents = policy.get("currents_c")
    switch_soc = policy.get("switch_soc", [])
    bounds = cfg["profile_bounds"]
    battery = cfg["battery"]

    if not isinstance(currents, list) or not all(isinstance(x, (int, float)) for x in currents):
        raise TypeError("currents_c must be a list of numbers")
    if not isinstance(switch_soc, list) or not all(isinstance(x, (int, float)) for x in switch_soc):
        raise TypeError("switch_soc must be a list of numbers")

    if not (int(bounds["min_stages"]) <= len(currents) <= int(bounds["max_stages"])):
        raise ValueError("stage count is outside configured bounds")
    if len(switch_soc) != len(currents) - 1:
        raise ValueError("switch_soc length must equal len(currents_c) - 1")

    currents_f = [float(x) for x in currents]
    switch_f = [float(x) for x in switch_soc]

    for current in currents_f:
        if not (float(bounds["min_current_c"]) <= current <= float(bounds["max_current_c"])):
            raise ValueError("each current must lie within configured current bounds")

    last = float(battery["initial_soc"])
    target_soc = float(battery["target_soc"])
    for threshold in switch_f:
        if not (float(bounds["min_switch_soc"]) < threshold < target_soc):
            raise ValueError("switch_soc thresholds must lie within configured SOC bounds")
        if threshold <= last:
            raise ValueError("switch_soc must be strictly increasing")
        last = threshold

    return currents_f, switch_f


def _simulate(currents_c: list[float], switch_soc: list[float], cfg: dict[str, Any]) -> dict[str, Any]:
    battery = cfg["battery"]
    limits = cfg["limits"]
    sim = cfg["simulation"]
    solid = cfg["solid_diffusion"]
    electrolyte = cfg["electrolyte"]
    kinetics = cfg["kinetics"]
    resistance = cfg["resistance"]
    thermal = cfg["thermal"]
    aging = cfg["aging"]
    scoring = cfg["scoring"]

    capacity_ah = float(battery["capacity_ah"])
    dt_s = float(sim["dt_s"])
    max_time_s = float(sim["max_time_s"])
    temp_ref_k = float(sim["temperature_ref_k"])
    ambient_temp_c = float(battery["ambient_temp_c"])
    cold_reference_c = temp_ref_k - 273.15

    soc = float(battery["initial_soc"])
    target_soc = float(battery["target_soc"])
    theta_n_avg = _theta_n_from_soc(soc, cfg)
    theta_p_avg = _theta_p_from_soc(soc, cfg)
    delta_theta_n = 0.0
    delta_theta_p = 0.0
    electrolyte_state = 0.0
    temp_c = ambient_temp_c
    temp_k = temp_c + 273.15
    plating_loss_ah = 0.0
    aging_loss_ah = 0.0
    max_temp_c = temp_c
    max_voltage_v = -1e9
    min_plating_margin_v = 1e9
    time_s = 0.0

    stage_idx = 0
    endpoints = list(switch_soc) + [target_soc]

    while time_s < max_time_s and soc < target_soc:
        while stage_idx < len(endpoints) - 1 and soc >= endpoints[stage_idx]:
            stage_idx += 1

        current_c = currents_c[stage_idx]
        current_a = current_c * capacity_ah

        temp_k = temp_c + 273.15
        scale_n = _arrhenius_scale(temp_k, temp_ref_k, float(solid["activation_energy_n_j_per_mol"]))
        scale_p = _arrhenius_scale(temp_k, temp_ref_k, float(solid["activation_energy_p_j_per_mol"]))
        scale_e = _arrhenius_scale(temp_k, temp_ref_k, float(electrolyte["activation_energy_j_per_mol"]))
        scale_k = _arrhenius_scale(temp_k, temp_ref_k, float(kinetics["activation_energy_j_per_mol"]))
        scale_r = 1.0 / _arrhenius_scale(temp_k, temp_ref_k, float(resistance["activation_energy_j_per_mol"]))
        scale_sei = _arrhenius_scale(temp_k, temp_ref_k, float(aging["sei_activation_energy_j_per_mol"]))

        tau_n = float(solid["tau_n_ref_s"]) / scale_n
        tau_p = float(solid["tau_p_ref_s"]) / scale_p
        tau_e = float(electrolyte["tau_ref_s"]) / scale_e

        delta_theta_n += dt_s * (
            float(solid["surface_gain_n_per_a"]) * current_a - delta_theta_n / max(tau_n, 1e-6)
        )
        delta_theta_p += dt_s * (
            -float(solid["surface_gain_p_per_a"]) * current_a - delta_theta_p / max(tau_p, 1e-6)
        )
        electrolyte_state += dt_s * (
            float(electrolyte["polarization_gain_per_a"]) * current_a - electrolyte_state / max(tau_e, 1e-6)
        )

        theta_n_surf = _clamp(theta_n_avg + delta_theta_n, 1e-5, 1.0 - 1e-5)
        theta_p_surf = _clamp(theta_p_avg + delta_theta_p, 1e-5, 1.0 - 1e-5)

        electrolyte_factor = max(
            0.2,
            1.0 - float(kinetics["electrolyte_factor"]) * abs(electrolyte_state),
        )
        i0_n = max(1e-6, float(kinetics["i0_n_ref_a"]) * scale_k * math.sqrt(theta_n_surf * (1.0 - theta_n_surf)) * electrolyte_factor)
        i0_p = max(1e-6, float(kinetics["i0_p_ref_a"]) * scale_k * math.sqrt(theta_p_surf * (1.0 - theta_p_surf)) * electrolyte_factor)

        eta_n = 2.0 * GAS_CONSTANT_J_PER_MOLK * temp_k / FARADAY_C_PER_MOL * math.asinh(current_a / (2.0 * i0_n))
        eta_p = 2.0 * GAS_CONSTANT_J_PER_MOLK * temp_k / FARADAY_C_PER_MOL * math.asinh(current_a / (2.0 * i0_p))

        avg_soc = _clamp(_soc_from_theta_n(theta_n_avg, cfg), 0.0, 1.0)
        high_soc_penalty = max(0.0, avg_soc - 0.7)
        low_soc_penalty = max(0.0, 0.2 - avg_soc)
        r_ohm = float(resistance["r_ohm_ref_ohm"]) * scale_r * (
            1.0
            + float(resistance["high_soc_coeff"]) * high_soc_penalty
            + float(resistance["low_soc_coeff"]) * low_soc_penalty
        )
        phi_e = float(electrolyte["phi_e_coeff_v"]) * electrolyte_state

        u_p = _ocv_positive(theta_p_surf, temp_k, cfg)
        u_n = _ocv_negative(theta_n_surf, temp_k, cfg)
        voc_v = u_p - u_n
        voltage_v = voc_v + eta_p + eta_n + current_a * r_ohm + phi_e
        max_voltage_v = max(max_voltage_v, voltage_v)

        plating_margin_v = (
            u_n
            - eta_n
            - 0.5 * phi_e
            - float(aging["temperature_penalty_coeff"]) * max(0.0, cold_reference_c - temp_c)
        )
        min_plating_margin_v = min(min_plating_margin_v, plating_margin_v)

        if voltage_v > float(limits["hard_voltage_cutoff_v"]):
            return {
                "valid": 0.0,
                "failure_reason": "voltage_cutoff",
                "charge_time_s": time_s,
                "max_temp_c": max_temp_c,
                "max_voltage_v": max_voltage_v,
                "min_plating_margin_v": min_plating_margin_v,
                "plating_loss_ah": plating_loss_ah,
                "aging_loss_ah": aging_loss_ah,
                "combined_score": 0.0,
            }

        if plating_margin_v < float(limits["hard_plating_margin_v"]):
            return {
                "valid": 0.0,
                "failure_reason": "plating_margin_cutoff",
                "charge_time_s": time_s,
                "max_temp_c": max_temp_c,
                "max_voltage_v": max_voltage_v,
                "min_plating_margin_v": min_plating_margin_v,
                "plating_loss_ah": plating_loss_ah,
                "aging_loss_ah": aging_loss_ah,
                "combined_score": 0.0,
            }

        plating_stress = max(0.0, float(limits["soft_plating_margin_v"]) - plating_margin_v)
        plating_loss_ah += (
            float(aging["plating_loss_coeff"])
            * current_a
            * plating_stress ** float(aging["plating_power"])
            * dt_s
            / 3600.0
        )

        sei_rate_ah_per_s = (
            float(aging["sei_rate_ref_ah_per_s"])
            * scale_sei
            * math.exp(float(aging["sei_stress_coeff"]) * max(0.0, float(aging["sei_margin_v"]) - plating_margin_v))
        )
        aging_loss_ah += sei_rate_ah_per_s * dt_s

        entropy_term = _entropy_term(theta_p_surf, theta_n_surf, cfg)
        heat_gen_w = abs(current_a * (voltage_v - voc_v)) + abs(
            current_a * temp_k * entropy_term
        ) * float(thermal["entropy_scale"])
        temp_c += dt_s * (
            heat_gen_w - float(thermal["h_a_w_per_k"]) * (temp_c - ambient_temp_c)
        ) / float(thermal["mass_cp_j_per_k"])
        max_temp_c = max(max_temp_c, temp_c)

        if temp_c > float(limits["hard_temp_c"]):
            return {
                "valid": 0.0,
                "failure_reason": "thermal_cutoff",
                "charge_time_s": time_s,
                "max_temp_c": max_temp_c,
                "max_voltage_v": max_voltage_v,
                "min_plating_margin_v": min_plating_margin_v,
                "plating_loss_ah": plating_loss_ah,
                "aging_loss_ah": aging_loss_ah,
                "combined_score": 0.0,
            }

        delta_soc = current_a * dt_s / (capacity_ah * 3600.0)
        soc = _clamp(soc + delta_soc, 0.0, 1.0)
        theta_n_avg = _theta_n_from_soc(soc, cfg)
        theta_p_avg = _theta_p_from_soc(soc, cfg)
        time_s += dt_s

    if soc < target_soc:
        return {
            "valid": 0.0,
            "failure_reason": "timeout",
            "charge_time_s": time_s,
            "max_temp_c": max_temp_c,
            "max_voltage_v": max_voltage_v,
            "min_plating_margin_v": min_plating_margin_v,
            "plating_loss_ah": plating_loss_ah,
            "aging_loss_ah": aging_loss_ah,
            "combined_score": 0.0,
        }

    time_score = math.exp(-(time_s - float(scoring["time_reference_s"])) / float(scoring["time_scale_s"]))
    aging_score = math.exp(-float(scoring["aging_coeff"]) * aging_loss_ah)
    plating_score = math.exp(-float(scoring["plating_coeff"]) * plating_loss_ah)
    thermal_score = math.exp(
        -max(0.0, max_temp_c - float(scoring["thermal_reference_c"])) / float(scoring["thermal_scale_c"])
    )
    voltage_score = math.exp(
        -max(0.0, max_voltage_v - float(limits["max_voltage_v"])) / float(scoring["voltage_scale_v"])
    )
    combined_score = float(scoring["score_scale"]) * (
        float(scoring["weight_time"]) * time_score
        + float(scoring["weight_aging"]) * aging_score
        + float(scoring["weight_plating"]) * plating_score
        + float(scoring["weight_thermal"]) * thermal_score
        + float(scoring["weight_voltage"]) * voltage_score
    )

    return {
        "valid": 1.0,
        "failure_reason": "",
        "charge_time_s": time_s,
        "max_temp_c": max_temp_c,
        "max_voltage_v": max_voltage_v,
        "min_plating_margin_v": min_plating_margin_v,
        "plating_loss_ah": plating_loss_ah,
        "aging_loss_ah": aging_loss_ah,
        "time_score": time_score,
        "aging_score": aging_score,
        "plating_score": plating_score,
        "thermal_score": thermal_score,
        "voltage_score": voltage_score,
        "combined_score": combined_score,
        "soft_temp_violation": 1.0 if max_temp_c > float(limits["soft_temp_c"]) else 0.0,
        "soft_voltage_violation": 1.0 if max_voltage_v > float(limits["max_voltage_v"]) else 0.0,
        "soft_plating_violation": 1.0 if min_plating_margin_v < float(limits["soft_plating_margin_v"]) else 0.0,
        "final_soc": soc,
    }


def evaluate(candidate_path: Path, config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    try:
        cfg = _load_config(config_path)
        policy = _load_candidate(candidate_path)
        currents_c, switch_soc = _validate_policy(policy, cfg)
        result = _simulate(currents_c, switch_soc, cfg)
        result["currents_c"] = currents_c
        result["switch_soc"] = switch_soc
        result["config_path"] = str(config_path.resolve())
        result["battery_name"] = str(cfg["battery"].get("name", "battery"))
        return result
    except Exception as exc:
        return {
            "valid": 0.0,
            "combined_score": 0.0,
            "failure_reason": f"exception: {exc}",
            "traceback": traceback.format_exc(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a SPMe-style battery fast-charging policy.")
    parser.add_argument("candidate", help="Path to candidate Python file")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to battery parameter JSON")
    parser.add_argument("--json-out", default=None, help="Optional path to metrics JSON")
    parser.add_argument("--artifacts-out", default=None, help="Optional path to artifacts JSON")
    args = parser.parse_args()

    candidate_path = Path(args.candidate).resolve()
    config_path = Path(args.config).resolve()
    result = evaluate(candidate_path, config_path=config_path)
    metrics = dict(result)
    metrics["candidate_path"] = str(candidate_path)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(metrics, indent=2, ensure_ascii=True), encoding="utf-8")

    if args.artifacts_out:
        artifacts = {
            "candidate_path": str(candidate_path),
            "config_path": str(config_path),
            "failure_reason": result.get("failure_reason", ""),
            "currents_c": result.get("currents_c", []),
            "switch_soc": result.get("switch_soc", []),
        }
        if "traceback" in result:
            artifacts["traceback"] = result["traceback"]
        Path(args.artifacts_out).write_text(json.dumps(artifacts, indent=2, ensure_ascii=True), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=True))


if __name__ == "__main__":
    main()
