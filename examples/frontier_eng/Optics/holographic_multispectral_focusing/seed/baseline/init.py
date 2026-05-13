# EVOLVE-BLOCK-START
"""Baseline solver for Task 3: multi-wavelength focusing/splitting."""

from __future__ import annotations

import math
from typing import Any

import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field, System
from torchoptics.elements import PolychromaticPhaseModulator
from torchoptics.profiles import gaussian


def make_default_spec() -> dict[str, Any]:
    waist = 130e-6
    return {
        "shape": 72,
        "spacing": 10e-6,
        "wavelengths": [450e-9, 520e-9, 590e-9, 660e-9],
        "waist_radius": waist,
        "layer_z": [0.0, 0.18, 0.36],
        "output_z": 0.62,
        "target_centers": [
            (-2.4 * waist, -0.8 * waist),
            (-0.8 * waist, 1.8 * waist),
            (0.9 * waist, -1.8 * waist),
            (2.3 * waist, 0.8 * waist),
        ],
        "target_spectral_ratios": [0.30, 0.24, 0.26, 0.20],
        "steps": 180,
        "lr": 0.07,
        "init_phase_std": 0.2,
        "xt_weight": 0.9,
        "shape_weight": 0.2,
        "spectral_weight": 0.8,
        "num_restarts": 3,
    }


def _build_system(spec: dict[str, Any], device: str) -> System:
    shape = int(spec["shape"])
    init_phase_std = float(spec.get("init_phase_std", 0.0))
    layers = [
        PolychromaticPhaseModulator(
            Parameter(init_phase_std * torch.randn((shape, shape), dtype=torch.double)),
            z=float(z),
        )
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


def _make_input_fields(spec: dict[str, Any], device: str) -> list[Field]:
    fields = []
    for wl in spec["wavelengths"]:
        field = Field(gaussian(spec["shape"], spec["waist_radius"]), wavelength=wl, z=0).normalize(1.0)
        fields.append(field.to(device))
    return fields


def _roi_power(field: Field, center: tuple[float, float], radius: float) -> torch.Tensor:
    x, y = field.meshgrid()
    intensity = field.intensity()
    mask = ((x - center[0]) ** 2 + (y - center[1]) ** 2) <= radius**2
    return (intensity * mask.to(intensity.dtype)).sum()


def _all_designated_powers(
    field: Field,
    centers: list[tuple[float, float]],
    radius: float,
) -> torch.Tensor:
    return torch.stack([_roi_power(field, center, radius) for center in centers])


def _cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    a_flat = a.flatten()
    b_flat = b.flatten()
    return torch.dot(a_flat, b_flat) / (torch.norm(a_flat) * torch.norm(b_flat) + 1e-12)


def _make_target_maps(spec: dict[str, Any], device: str) -> list[torch.Tensor]:
    target_maps: list[torch.Tensor] = []
    for center in spec["target_centers"]:
        target_map = gaussian(spec["shape"], spec["waist_radius"], offset=center).real.to(device)
        target_maps.append(target_map / (target_map.sum() + 1e-12))
    return target_maps


def _score_solution(
    system: System,
    input_fields: list[Field],
    target_maps: list[torch.Tensor],
    target_spectral: torch.Tensor,
    spec: dict[str, Any],
    roi_radius: float,
) -> float:
    target_powers = []
    per_wavelength_eff = []
    per_wavelength_xt = []
    per_wavelength_shape = []

    for idx, (field, target_map) in enumerate(zip(input_fields, target_maps)):
        out = system.measure_at_z(field, z=spec["output_z"])
        all_designated = _all_designated_powers(out, spec["target_centers"], roi_radius)
        target_power = all_designated[idx]
        target_powers.append(target_power)

        total_power = out.intensity().sum() + 1e-12
        designated_total = all_designated.sum() + 1e-12
        pred_norm = out.intensity() / total_power

        per_wavelength_eff.append(float((target_power / total_power).item()))
        per_wavelength_xt.append(float(((designated_total - target_power) / designated_total).item()))
        per_wavelength_shape.append(float(_cosine_similarity(pred_norm, target_map).item()))

    pred_spectral = torch.stack(target_powers)
    pred_spectral = pred_spectral / (pred_spectral.sum() + 1e-12)
    spectral_ratio_mae = float(torch.mean(torch.abs(pred_spectral - target_spectral)).item())

    mean_eff = sum(per_wavelength_eff) / len(per_wavelength_eff)
    mean_xt = sum(per_wavelength_xt) / len(per_wavelength_xt)
    mean_shape_cosine = sum(per_wavelength_shape) / len(per_wavelength_shape)

    efficiency_score = float(min(1.0, max(0.0, mean_eff / float(spec.get("score_eff_target", 0.06)))))
    isolation_score = float(min(1.0, max(0.0, 1.0 - mean_xt)))
    spectral_score = float(math.exp(-spectral_ratio_mae / float(spec.get("score_spectral_scale", 0.10))))
    score = (
        (efficiency_score**0.45)
        * (isolation_score**0.25)
        * (spectral_score**0.20)
        * (mean_shape_cosine**0.10)
    )
    return float(min(1.0, max(0.0, score)))


def solve(spec: dict[str, Any] | None = None, device: str | None = None, seed: int = 0) -> dict[str, Any]:
    spec = {**make_default_spec(), **(spec or {})}
    device = device or "cpu"
    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelengths"][1])

    roi_radius = float(spec.get("roi_radius_m", 4 * spec["spacing"]))
    xt_weight = float(spec.get("xt_weight", 0.9))
    shape_weight = float(spec.get("shape_weight", 0.2))
    spectral_weight = float(spec.get("spectral_weight", 0.8))
    num_restarts = max(int(spec.get("num_restarts", 1)), 1)
    input_fields = _make_input_fields(spec, device)
    target_maps = _make_target_maps(spec, device)
    target_spectral = torch.tensor(spec["target_spectral_ratios"], dtype=torch.double, device=device)
    target_spectral = target_spectral / target_spectral.sum()
    best_system: System | None = None
    best_losses: list[float] = []
    best_score = float("-inf")

    # Try a few fixed restarts because shared-mask optimization is sensitive to initialization.
    for restart_idx in range(num_restarts):
        torch.manual_seed(seed + restart_idx)
        system = _build_system(spec, device)
        optimizer = torch.optim.Adam(system.parameters(), lr=float(spec["lr"]))
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=max(int(spec["steps"]), 1),
        )
        losses: list[float] = []

        for _ in range(int(spec["steps"])):
            optimizer.zero_grad()

            target_powers = []
            per_wavelength_losses = []
            for idx, (field, target_map) in enumerate(zip(input_fields, target_maps)):
                out = system.measure_at_z(field, z=spec["output_z"])
                all_designated = _all_designated_powers(out, spec["target_centers"], roi_radius)
                target_power = all_designated[idx]
                target_powers.append(target_power)
                total_power = out.intensity().sum() + 1e-12
                other_designated_power = all_designated.sum() - target_power
                pred_norm = out.intensity() / total_power
                shape_cosine = _cosine_similarity(pred_norm, target_map)
                per_wavelength_losses.append(
                    (1.0 - target_power / total_power)
                    + xt_weight * (other_designated_power / total_power)
                    + shape_weight * (1.0 - shape_cosine)
                )

            pred_spectral = torch.stack(target_powers)
            pred_spectral = pred_spectral / (pred_spectral.sum() + 1e-12)
            spectral_loss = torch.mean(torch.abs(pred_spectral - target_spectral))
            loss = torch.stack(per_wavelength_losses).mean() + spectral_weight * spectral_loss
            loss.backward()
            optimizer.step()
            scheduler.step()

            losses.append(float(loss.item()))

        score = _score_solution(system, input_fields, target_maps, target_spectral, spec, roi_radius)
        if score > best_score:
            best_score = score
            best_system = system
            best_losses = losses

    if best_system is None:
        raise RuntimeError("Failed to optimize a baseline optical system.")

    return {
        "spec": spec,
        "system": best_system,
        "input_fields": input_fields,
        "loss_history": best_losses,
    }
# EVOLVE-BLOCK-END
