#!/usr/bin/env python3
"""Evaluator for DawnAircraftDesignOptimization."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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


def load_config(task_root: Path) -> dict:
    cfg_path = task_root / "references" / "mission_config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Missing config: {cfg_path}")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def standard_atmosphere_density(altitude_m: float, constants: dict) -> float:
    g = float(constants["gravity_mps2"])
    rho0 = float(constants["rho0_kgpm3"])
    t0 = float(constants["temperature0_k"])
    lapse = float(constants["lapse_rate_kpm"])
    r_air = float(constants["gas_constant_air"])

    h = float(max(0.0, altitude_m))
    if h <= 11000.0:
        t = t0 - lapse * h
        expn = g / (r_air * lapse) - 1.0
        return float(max(1e-5, rho0 * (t / t0) ** expn))

    t11 = t0 - lapse * 11000.0
    expn = g / (r_air * lapse) - 1.0
    rho11 = rho0 * (t11 / t0) ** expn
    rho = rho11 * math.exp(-g * (h - 11000.0) / (r_air * t11))
    return float(max(1e-5, rho))


def parse_submission(path: Path, bounds: dict[str, list[float]]) -> tuple[dict[str, float], str | None]:
    if not path.is_file():
        return {}, f"submission not found: {path}"

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"invalid JSON submission: {exc}"

    if not isinstance(payload, dict):
        return {}, "submission must be a JSON object"

    design: dict[str, float] = {}
    for key in DESIGN_KEYS:
        if key not in payload:
            return {}, f"missing key: {key}"
        try:
            value = float(payload[key])
        except Exception:
            return {}, f"non-numeric key: {key}"
        if not np.isfinite(value):
            return {}, f"non-finite key: {key}"

        lo, hi = bounds[key]
        if value < float(lo) or value > float(hi):
            return {}, f"{key} out of bounds [{lo}, {hi}]: {value}"
        design[key] = value

    return design, None


def evaluate_design(design: dict[str, float], cfg: dict) -> tuple[dict[str, float], dict[str, float]]:
    mission = cfg["mission"]
    c = cfg["constants"]
    cstr = cfg["constraints"]

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

    margins = {
        "aspect_ratio_min_margin": float(aspect_ratio - float(cstr["min_aspect_ratio"])),
        "aspect_ratio_max_margin": float(float(cstr["max_aspect_ratio"]) - aspect_ratio),
        "fineness_margin": float(
            fuselage_length_m / max(fuselage_diameter_m, 1e-6) - float(cstr["min_fuselage_fineness"])
        ),
        "takeoff_distance_margin_m": float(float(cstr["max_takeoff_distance_m"]) - takeoff_distance_m),
        "stall_speed_margin_mps": float(float(cstr["max_stall_speed_mps"]) - stall_speed_mps),
        "lift_margin": float(float(c["cl_max_cruise"]) - cl_cruise),
        "stress_margin_pa": float(float(cstr["allowable_root_stress_pa"]) - root_stress_pa),
        "energy_margin_j": float(usable_energy_j - required_energy_j),
        "power_margin_w": float(
            motor_power_kw * 1000.0 * float(cstr["required_power_headroom_fraction"]) - cruise_power_required_w
        ),
        "wing_loading_margin_n_m2": float(float(cstr["max_wing_loading_n_m2"]) - wing_loading_n_m2),
    }

    feasible = all(np.isfinite(v) and v >= 0.0 for v in margins.values())

    result = {
        "total_mass_kg": float(total_mass_kg),
        "cruise_power_kw": float(cruise_power_required_w / 1000.0),
        "takeoff_distance_m": float(takeoff_distance_m),
        "stall_speed_mps": float(stall_speed_mps),
        "aspect_ratio": float(aspect_ratio),
        "root_stress_pa": float(root_stress_pa),
        "usable_energy_kwh": float(usable_energy_j / 3.6e6),
        "required_energy_kwh": float(required_energy_j / 3.6e6),
        "feasible": float(1.0 if feasible else 0.0),
    }
    return result, margins


def run_candidate(candidate_path: Path, task_root: Path, timeout_s: float) -> tuple[dict[str, Any], dict[str, Any]]:
    work_dir = Path(tempfile.mkdtemp(prefix="dawn_aircraft_eval_")).resolve()
    artifacts: dict[str, Any] = {"work_dir": str(work_dir)}
    outcome: dict[str, Any] = {
        "ok": False,
        "submission_path": None,
        "stdout": "",
        "stderr": "",
        "returncode": -1,
        "error": None,
        "work_dir": str(work_dir),
    }

    try:
        target = work_dir / "init.py"
        shutil.copy2(candidate_path, target)
        shutil.copytree(task_root / "references", work_dir / "references")

        proc = subprocess.run(
            [sys.executable, str(target)],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        outcome["stdout"] = proc.stdout
        outcome["stderr"] = proc.stderr
        outcome["returncode"] = int(proc.returncode)

        if proc.returncode != 0:
            outcome["error"] = f"candidate exited with code {proc.returncode}"
            return outcome, artifacts

        submission_path = work_dir / "submission.json"
        if not submission_path.is_file():
            outcome["error"] = "candidate did not generate submission.json"
            return outcome, artifacts

        outcome["ok"] = True
        outcome["submission_path"] = str(submission_path)
        return outcome, artifacts

    except subprocess.TimeoutExpired:
        outcome["error"] = f"candidate timed out after {timeout_s:.1f}s"
        return outcome, artifacts
    except Exception as exc:
        outcome["error"] = f"candidate execution failed: {exc}"
        return outcome, artifacts


def write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate DawnAircraftDesignOptimization candidate.")
    parser.add_argument("candidate", nargs="?", default=None, help="Path to candidate script (e.g., scripts/init.py)")
    parser.add_argument("--submission", default="submission.json", help="Submission path when no candidate is given")
    parser.add_argument("--metrics-out", default=None, help="Optional metrics JSON output path")
    parser.add_argument("--artifacts-out", default=None, help="Optional artifacts JSON output path")
    parser.add_argument("--timeout-s", type=float, default=180.0, help="Candidate execution timeout in seconds")
    args = parser.parse_args()

    start = time.time()
    task_root = Path(__file__).resolve().parents[1]
    cfg = load_config(task_root)

    artifacts: dict[str, Any] = {}
    candidate_stdout = ""
    candidate_stderr = ""
    returncode = 0

    if args.candidate is not None:
        candidate_path = Path(args.candidate).expanduser().resolve()
        if not candidate_path.is_file():
            metrics = {
                "combined_score": 0.0,
                "valid": 0.0,
                "feasible": 0.0,
                "runtime_s": float(time.time() - start),
            }
            artifacts["error_message"] = f"candidate not found: {candidate_path}"
            write_json(args.metrics_out, metrics)
            write_json(args.artifacts_out, artifacts)
            print(json.dumps({"score": 0.0, "valid": 0.0, "error": artifacts["error_message"]}, ensure_ascii=False))
            return 1

        run_outcome, run_artifacts = run_candidate(candidate_path, task_root, timeout_s=float(args.timeout_s))
        artifacts.update(run_artifacts)
        candidate_stdout = str(run_outcome.get("stdout", ""))
        candidate_stderr = str(run_outcome.get("stderr", ""))
        returncode = int(run_outcome.get("returncode", -1))

        artifacts["candidate_stdout"] = candidate_stdout[-8000:]
        artifacts["candidate_stderr"] = candidate_stderr[-8000:]

        if not bool(run_outcome.get("ok", False)):
            metrics = {
                "combined_score": 0.0,
                "valid": 0.0,
                "feasible": 0.0,
                "candidate_returncode": float(returncode),
                "runtime_s": float(time.time() - start),
            }
            artifacts["error_message"] = str(run_outcome.get("error", "candidate execution failed"))
            write_json(args.metrics_out, metrics)
            write_json(args.artifacts_out, artifacts)
            print(json.dumps({"score": 0.0, "valid": 0.0, "error": artifacts["error_message"]}, ensure_ascii=False))
            return 1

        submission_path = Path(str(run_outcome["submission_path"]))
    else:
        submission_path = Path(args.submission).expanduser().resolve()

    design, error = parse_submission(submission_path, cfg["bounds"])
    if error is not None:
        metrics = {
            "combined_score": 0.0,
            "valid": 0.0,
            "feasible": 0.0,
            "candidate_returncode": float(returncode),
            "runtime_s": float(time.time() - start),
        }
        artifacts["error_message"] = error
        write_json(args.metrics_out, metrics)
        write_json(args.artifacts_out, artifacts)
        print(json.dumps({"score": 0.0, "valid": 0.0, "error": error}, ensure_ascii=False))
        return 1

    result, margins = evaluate_design(design, cfg)
    feasible = bool(result["feasible"] > 0.5)
    mass_ref = float(cfg.get("scoring", {}).get("mass_reference_kg", 400.0))
    combined_score = float(mass_ref / (mass_ref + result["total_mass_kg"])) if feasible else 0.0

    metrics = {
        "combined_score": combined_score,
        "valid": float(1.0 if feasible else 0.0),
        "feasible": float(1.0 if feasible else 0.0),
        "total_mass_kg": float(result["total_mass_kg"]),
        "cruise_power_kw": float(result["cruise_power_kw"]),
        "takeoff_distance_m": float(result["takeoff_distance_m"]),
        "stall_speed_mps": float(result["stall_speed_mps"]),
        "aspect_ratio": float(result["aspect_ratio"]),
        "runtime_s": float(time.time() - start),
        "candidate_returncode": float(returncode),
    }

    artifacts["submission"] = design
    artifacts["result"] = result
    artifacts["constraint_margins"] = margins
    artifacts["failure_summary"] = (
        "none" if feasible else "one or more constraints violated; inspect constraint_margins"
    )

    write_json(args.metrics_out, metrics)
    write_json(args.artifacts_out, artifacts)

    print(
        json.dumps(
            {
                "score": combined_score,
                "valid": float(1.0 if feasible else 0.0),
                "total_mass_kg": result["total_mass_kg"],
                "cruise_power_kw": result["cruise_power_kw"],
            },
            ensure_ascii=False,
        )
    )

    return 0 if feasible else 1


if __name__ == "__main__":
    raise SystemExit(main())
