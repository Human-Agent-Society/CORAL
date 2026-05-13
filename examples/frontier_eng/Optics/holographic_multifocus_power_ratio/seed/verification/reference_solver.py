"""Third-party oracle solver for Task 1.

Pipeline:
1) Use slmsuite WGS to produce a strong phase seed.
2) Fine-tune in torchoptics with ratio/leakage-aware objective.
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


def _build_target_field(spec: dict[str, Any], device: str) -> Field:
    shape = int(spec["shape"])
    waist = float(spec["waist_radius"])
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)

    ratios = torch.tensor(spec["focus_ratios"], dtype=torch.double, device=device)
    ratios = ratios / ratios.sum()

    for ratio, center in zip(ratios, spec["focus_centers"]):
        target += torch.sqrt(ratio) * gaussian(shape, waist, offset=center).real.to(device)

    return Field(target.to(torch.cdouble), z=spec["output_z"]).normalize(1.0)


def _build_system(spec: dict[str, Any], device: str) -> System:
    shape = int(spec["shape"])
    layers = [
        PhaseModulator(Parameter(torch.zeros((shape, shape), dtype=torch.double)), z=float(z))
        for z in spec["layer_z"]
    ]
    return System(*layers).to(device)


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


def _slmsuite_seed_phase(spec: dict[str, Any]) -> torch.Tensor:
    from slmsuite.holography.algorithms import Hologram

    shape = int(spec["shape"])
    spacing = float(spec["spacing"])

    yy, xx = np.mgrid[0:shape, 0:shape]
    target = np.zeros((shape, shape), dtype=np.float32)

    ratios = np.array(spec["focus_ratios"], dtype=np.float64)
    ratios = ratios / ratios.sum()

    sigma_pix = float(spec.get("oracle_sigma_pix", 2.0))
    for ratio, (cx_m, cy_m) in zip(ratios, spec["focus_centers"]):
        x_idx = _coord_to_index(cx_m, shape, spacing)
        y_idx = _coord_to_index(cy_m, shape, spacing)
        target += np.sqrt(ratio) * np.exp(-((yy - y_idx) ** 2 + (xx - x_idx) ** 2) / (2.0 * sigma_pix**2))
    target = target + 1e-6

    hologram = Hologram(target=target, slm_shape=(shape, shape))
    hologram.optimize(method=spec.get("oracle_method", "WGS-Kim"), maxiter=int(spec.get("oracle_wgs_iters", 120)), verbose=False)

    return torch.from_numpy(hologram.get_phase()).to(torch.double)


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    input_field = Field(gaussian(spec["shape"], spec["waist_radius"]), z=0).normalize(1.0).to(device)
    target_field = _build_target_field(spec, device)
    system = _build_system(spec, device)

    seed_phase = _slmsuite_seed_phase(spec).to(device)
    with torch.no_grad():
        system[0].phase.copy_(seed_phase)
        if len(system) > 1:
            system[1].phase.copy_(0.5 * seed_phase)

    target_ratios = torch.tensor(spec["focus_ratios"], dtype=torch.double, device=device)
    target_ratios = target_ratios / target_ratios.sum()
    roi_radius = float(spec["roi_radius_m"])

    steps = int(spec.get("reference_steps", 220))
    lr = float(spec.get("reference_lr", 0.06))

    optimizer = torch.optim.Adam(system.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps)
    losses: list[float] = []

    for _ in range(steps):
        optimizer.zero_grad()
        output_field = system.measure_at_z(input_field, z=spec["output_z"])

        overlap_loss = 1.0 - output_field.inner(target_field).abs().square()

        powers = _roi_powers(output_field, spec["focus_centers"], roi_radius)
        total_power = output_field.intensity().sum() + 1e-12
        focus_power = powers.sum()

        ratio_hat = powers / (focus_power + 1e-12)
        ratio_loss = torch.mean(torch.abs(ratio_hat - target_ratios))
        leakage_loss = 1.0 - focus_power / total_power

        phase_reg = torch.tensor(0.0, dtype=torch.double, device=device)
        for layer in system:
            dx = layer.phase[:, 1:] - layer.phase[:, :-1]
            dy = layer.phase[1:, :] - layer.phase[:-1, :]
            phase_reg = phase_reg + (dx.abs().mean() + dy.abs().mean())

        loss = 0.35 * overlap_loss + 0.95 * ratio_loss + 0.45 * leakage_loss + 1e-3 * phase_reg
        loss.backward()
        optimizer.step()
        scheduler.step()

        losses.append(float(loss.item()))

    return {
        "spec": spec,
        "system": system,
        "input_field": input_field,
        "target_field": target_field,
        "loss_history": losses,
        "oracle_backend": "slmsuite_wgs+torchoptics_finetune",
    }
