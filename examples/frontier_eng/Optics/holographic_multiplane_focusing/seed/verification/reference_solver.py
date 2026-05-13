"""Third-party oracle solver for Task 2.

Pipeline:
1) Use slmsuite WGS per target plane to generate phase seeds.
2) Fuse seeds into multi-layer initialization.
3) Fine-tune with multi-plane ratio/leakage-aware objective.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field, System
from torchoptics.elements import PhaseModulator
from torchoptics.profiles import gaussian


def _build_system(spec: dict[str, Any], device: str) -> System:
    shape = int(spec["shape"])
    layers = [
        PhaseModulator(Parameter(torch.zeros((shape, shape), dtype=torch.double)), z=float(z))
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


def _build_target_field_for_plane(spec: dict[str, Any], plane_cfg: dict[str, Any], device: str) -> Field:
    shape = int(spec["shape"])
    waist = float(spec["waist_radius"])

    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratios = torch.tensor(plane_cfg["ratios"], dtype=torch.double, device=device)
    ratios = ratios / ratios.sum()

    for ratio, center in zip(ratios, plane_cfg["centers"]):
        target += torch.sqrt(ratio) * gaussian(shape, waist, offset=center).real.to(device)

    return Field(target.to(torch.cdouble), z=plane_cfg["z"]).normalize(1.0)


def _roi_powers(field: Field, centers: list[tuple[float, float]], radius: float) -> torch.Tensor:
    x, y = field.meshgrid()
    intensity = field.intensity()
    powers = []
    for cx, cy in centers:
        mask = (((x - cx) ** 2 + (y - cy) ** 2) <= radius**2).to(intensity.dtype)
        powers.append((intensity * mask).sum())
    return torch.stack(powers)


def _coord_to_index(coord_m: float, shape: int, spacing: float) -> int:
    idx = int(round(coord_m / spacing + (shape - 1) / 2.0))
    return int(np.clip(idx, 0, shape - 1))


def _slmsuite_seed_phase_for_plane(spec: dict[str, Any], plane_cfg: dict[str, Any]) -> torch.Tensor:
    from slmsuite.holography.algorithms import Hologram

    shape = int(spec["shape"])
    spacing = float(spec["spacing"])
    yy, xx = np.mgrid[0:shape, 0:shape]

    target = np.zeros((shape, shape), dtype=np.float32)
    ratios = np.array(plane_cfg["ratios"], dtype=np.float64)
    ratios = ratios / ratios.sum()

    sigma_pix = float(spec.get("oracle_sigma_pix", 2.0))
    for ratio, (x_m, y_m) in zip(ratios, plane_cfg["centers"]):
        x_idx = _coord_to_index(x_m, shape, spacing)
        y_idx = _coord_to_index(y_m, shape, spacing)
        target += np.sqrt(ratio) * np.exp(-((yy - y_idx) ** 2 + (xx - x_idx) ** 2) / (2.0 * sigma_pix**2))
    target = target + 1e-6

    hologram = Hologram(target=target, slm_shape=(shape, shape))
    hologram.optimize(method=spec.get("oracle_method", "WGS-Kim"), maxiter=int(spec.get("oracle_wgs_iters", 100)), verbose=False)
    return torch.from_numpy(hologram.get_phase()).to(torch.double)


def _initialize_from_plane_seeds(system: System, spec: dict[str, Any], device: str) -> None:
    seeds = [_slmsuite_seed_phase_for_plane(spec, plane_cfg).to(device) for plane_cfg in spec["planes"]]

    with torch.no_grad():
        if len(system) == 1:
            system[0].phase.copy_(seeds[0])
            return

        # layer 0: average seed, layer 1: differential seed, others: low-weight average
        avg_seed = torch.stack(seeds).mean(dim=0)
        system[0].phase.copy_(avg_seed)

        if len(system) >= 2:
            diff_seed = seeds[0] - seeds[-1]
            system[1].phase.copy_(0.5 * diff_seed)

        for idx in range(2, len(system)):
            system[idx].phase.copy_(0.25 * avg_seed)


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    input_field = Field(gaussian(spec["shape"], spec["waist_radius"]), z=0).normalize(1.0).to(device)
    system = _build_system(spec, device)
    target_fields = [_build_target_field_for_plane(spec, p, device) for p in spec["planes"]]

    _initialize_from_plane_seeds(system, spec, device)

    roi_radius = float(spec["roi_radius_m"])
    steps = int(spec.get("reference_steps", 240))
    lr = float(spec.get("reference_lr", 0.05))

    optimizer = torch.optim.Adam(system.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps)
    losses: list[float] = []

    for _ in range(steps):
        optimizer.zero_grad()

        per_plane_losses = []
        for plane_cfg, target_field in zip(spec["planes"], target_fields):
            output = system.measure_at_z(input_field, z=plane_cfg["z"])

            overlap_loss = 1.0 - output.inner(target_field).abs().square()

            powers = _roi_powers(output, plane_cfg["centers"], roi_radius)
            focus_power = powers.sum()
            total_power = output.intensity().sum() + 1e-12
            pred_ratios = powers / (focus_power + 1e-12)

            target_ratios = torch.tensor(plane_cfg["ratios"], dtype=torch.double, device=device)
            target_ratios = target_ratios / target_ratios.sum()

            ratio_loss = torch.mean(torch.abs(pred_ratios - target_ratios))
            leakage_loss = 1.0 - focus_power / total_power

            per_plane_losses.append(0.40 * overlap_loss + 0.95 * ratio_loss + 0.35 * leakage_loss)

        per_plane_losses_t = torch.stack(per_plane_losses)
        weights = torch.softmax(per_plane_losses_t.detach() / 0.20, dim=0)
        loss = (weights * per_plane_losses_t).sum()

        loss.backward()
        optimizer.step()
        scheduler.step()

        losses.append(float(loss.item()))

    return {
        "spec": spec,
        "system": system,
        "input_field": input_field,
        "target_fields": target_fields,
        "loss_history": losses,
        "oracle_backend": "slmsuite_wgs_per_plane+torchoptics_finetune",
    }
