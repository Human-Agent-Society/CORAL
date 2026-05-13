"""Third-party oracle solver for Task 4.

Pipeline:
1) Solve two scalar holograms with slmsuite (x-pattern and y-pattern).
2) Initialize diagonal Jones phases from these holograms.
3) Fine-tune with polarization crosstalk-aware objective.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field, PlanarGrid
from torchoptics.profiles import gaussian


def _build_input_fields(spec: dict[str, Any], device: str) -> tuple[Field, Field]:
    shape = int(spec["shape"])
    base = gaussian(shape, spec["waist_radius"])

    data_x = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_y = torch.zeros((3, shape, shape), dtype=torch.cdouble)
    data_x[0] = base.to(torch.cdouble)
    data_y[1] = base.to(torch.cdouble)

    field_x = Field(data_x, wavelength=spec["wavelength"], z=0).normalize(1.0).to(device)
    field_y = Field(data_y, wavelength=spec["wavelength"], z=0).normalize(1.0).to(device)
    return field_x, field_y


def _build_target_map(
    shape: int,
    waist: float,
    centers: list[tuple[float, float]],
    ratios: list[float],
    device: str,
) -> torch.Tensor:
    target = torch.zeros((shape, shape), dtype=torch.double, device=device)
    ratio_t = torch.tensor(ratios, dtype=torch.double, device=device)
    ratio_t = ratio_t / ratio_t.sum()
    for ratio, center in zip(ratio_t, centers):
        target += ratio * gaussian(shape, waist, offset=center).real.to(device)
    return target / (target.sum() + 1e-12)


def _jones_from_phase(phase_x: torch.Tensor, phase_y: torch.Tensor) -> torch.Tensor:
    shape = phase_x.shape
    jones = torch.zeros((3, 3, shape[0], shape[1]), dtype=torch.cdouble, device=phase_x.device)
    jones[0, 0] = torch.exp(1j * phase_x)
    jones[1, 1] = torch.exp(1j * phase_y)
    jones[2, 2] = 1.0 + 0j
    return jones


def _forward(
    field: Field,
    spec: dict[str, Any],
    phase_x_layers: list[Parameter],
    phase_y_layers: list[Parameter],
) -> Field:
    out = field
    for z, phase_x, phase_y in zip(spec["layer_z"], phase_x_layers, phase_y_layers):
        out = out.propagate_to_z(z)
        out = out.polarized_modulate(_jones_from_phase(phase_x, phase_y))
    return out.propagate_to_z(spec["output_z"])


def _build_pattern_masks(spec: dict[str, Any], device: str) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
    plane = PlanarGrid(spec["shape"], spec["output_z"], spacing=spec["spacing"]).to(device)
    x, y = plane.meshgrid()
    radius = float(spec["roi_radius_m"])

    masks_x = [(((x - cx) ** 2 + (y - cy) ** 2) <= radius**2).to(torch.double) for cx, cy in spec["pattern_x_centers"]]
    masks_y = [(((x - cx) ** 2 + (y - cy) ** 2) <= radius**2).to(torch.double) for cx, cy in spec["pattern_y_centers"]]
    return masks_x, masks_y


def _sum_on_masks(map_intensity: torch.Tensor, masks: list[torch.Tensor]) -> torch.Tensor:
    return torch.stack([(map_intensity * m).sum() for m in masks]).sum()


def _powers_on_masks(map_intensity: torch.Tensor, masks: list[torch.Tensor]) -> torch.Tensor:
    return torch.stack([(map_intensity * m).sum() for m in masks])


def _coord_to_index(coord_m: float, shape: int, spacing: float) -> int:
    idx = int(round(coord_m / spacing + (shape - 1) / 2.0))
    return int(np.clip(idx, 0, shape - 1))


def _slmsuite_phase_from_pattern(
    shape: int,
    spacing: float,
    centers: list[tuple[float, float]],
    ratios: list[float],
    sigma_pix: float,
    seed: int,
) -> torch.Tensor:
    from slmsuite.holography.algorithms import Hologram

    yy, xx = np.mgrid[0:shape, 0:shape]
    target = np.zeros((shape, shape), dtype=np.float32)

    r = np.array(ratios, dtype=np.float64)
    r = r / r.sum()
    for ratio, (x_m, y_m) in zip(r, centers):
        x_idx = _coord_to_index(x_m, shape, spacing)
        y_idx = _coord_to_index(y_m, shape, spacing)
        target += np.sqrt(ratio) * np.exp(-((yy - y_idx) ** 2 + (xx - x_idx) ** 2) / (2.0 * sigma_pix**2))
    target = target + 1e-6

    np.random.seed(seed)
    hologram = Hologram(target=target, slm_shape=(shape, shape))
    hologram.optimize(method="WGS-Kim", maxiter=100, verbose=False)
    return torch.from_numpy(hologram.get_phase()).to(torch.double)


def solve(spec: dict[str, Any], device: str | None = None, seed: int = 0) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torchoptics.set_default_spacing(spec["spacing"])
    torchoptics.set_default_wavelength(spec["wavelength"])

    shape = int(spec["shape"])
    field_x, field_y = _build_input_fields(spec, device)

    target_x = _build_target_map(
        shape,
        spec["waist_radius"],
        spec["pattern_x_centers"],
        spec["pattern_x_ratios"],
        device,
    )
    target_y = _build_target_map(
        shape,
        spec["waist_radius"],
        spec["pattern_y_centers"],
        spec["pattern_y_ratios"],
        device,
    )

    masks_x, masks_y = _build_pattern_masks(spec, device)

    phase_x_layers = [Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device)) for _ in spec["layer_z"]]
    phase_y_layers = [Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device)) for _ in spec["layer_z"]]

    seed_phase_x = _slmsuite_phase_from_pattern(
        shape,
        float(spec["spacing"]),
        spec["pattern_x_centers"],
        spec["pattern_x_ratios"],
        sigma_pix=2.0,
        seed=seed,
    ).to(device)
    seed_phase_y = _slmsuite_phase_from_pattern(
        shape,
        float(spec["spacing"]),
        spec["pattern_y_centers"],
        spec["pattern_y_ratios"],
        sigma_pix=2.0,
        seed=seed + 17,
    ).to(device)

    with torch.no_grad():
        for px in phase_x_layers:
            px.copy_(seed_phase_x / len(phase_x_layers))
        for py in phase_y_layers:
            py.copy_(seed_phase_y / len(phase_y_layers))

    steps = int(spec.get("reference_steps", 280))
    lr = float(spec.get("reference_lr", 0.045))
    optimizer = torch.optim.Adam([*phase_x_layers, *phase_y_layers], lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps)
    target_ratio_x = torch.tensor(spec["pattern_x_ratios"], dtype=torch.double, device=device)
    target_ratio_x = target_ratio_x / target_ratio_x.sum()
    target_ratio_y = torch.tensor(spec["pattern_y_ratios"], dtype=torch.double, device=device)
    target_ratio_y = target_ratio_y / target_ratio_y.sum()

    losses: list[float] = []

    for _ in range(steps):
        optimizer.zero_grad()

        out_x = _forward(field_x, spec, phase_x_layers, phase_y_layers)
        out_y = _forward(field_y, spec, phase_x_layers, phase_y_layers)

        map_x = out_x.intensity().sum(dim=-3)
        map_y = out_y.intensity().sum(dim=-3)

        map_x_norm = map_x / (map_x.sum() + 1e-12)
        map_y_norm = map_y / (map_y.sum() + 1e-12)

        match_loss = torch.mean((map_x_norm - target_x) ** 2) + torch.mean((map_y_norm - target_y) ** 2)

        p_x_on_x = _sum_on_masks(map_x, masks_x)
        p_x_on_y = _sum_on_masks(map_x, masks_y)
        p_y_on_x = _sum_on_masks(map_y, masks_x)
        p_y_on_y = _sum_on_masks(map_y, masks_y)
        p_x_focus = _powers_on_masks(map_x, masks_x)
        p_y_focus = _powers_on_masks(map_y, masks_y)
        ratio_x = p_x_focus / (p_x_focus.sum() + 1e-12)
        ratio_y = p_y_focus / (p_y_focus.sum() + 1e-12)

        crosstalk_loss = 0.5 * (
            p_x_on_y / (p_x_on_x + p_x_on_y + 1e-12)
            + p_y_on_x / (p_y_on_x + p_y_on_y + 1e-12)
        )
        ratio_loss = torch.mean(torch.abs(ratio_x - target_ratio_x)) + torch.mean(torch.abs(ratio_y - target_ratio_y))
        own_efficiency = 0.5 * (
            p_x_on_x / (map_x.sum() + 1e-12)
            + p_y_on_y / (map_y.sum() + 1e-12)
        )
        focus_eff_loss = 1.0 - own_efficiency

        smooth_reg = torch.tensor(0.0, dtype=torch.double, device=device)
        for px, py in zip(phase_x_layers, phase_y_layers):
            smooth_reg = smooth_reg + (px[:, 1:] - px[:, :-1]).abs().mean()
            smooth_reg = smooth_reg + (px[1:, :] - px[:-1, :]).abs().mean()
            smooth_reg = smooth_reg + (py[:, 1:] - py[:, :-1]).abs().mean()
            smooth_reg = smooth_reg + (py[1:, :] - py[:-1, :]).abs().mean()

        loss = match_loss + 0.90 * crosstalk_loss + 0.35 * ratio_loss + 0.25 * focus_eff_loss + 1e-3 * smooth_reg
        loss.backward()
        optimizer.step()
        scheduler.step()

        losses.append(float(loss.item()))

    out_x = _forward(field_x, spec, phase_x_layers, phase_y_layers)
    out_y = _forward(field_y, spec, phase_x_layers, phase_y_layers)

    return {
        "spec": spec,
        "input_field_x": field_x,
        "input_field_y": field_y,
        "target_map_x": target_x.detach().cpu(),
        "target_map_y": target_y.detach().cpu(),
        "output_field_x": out_x,
        "output_field_y": out_y,
        "phase_x_layers": [p.detach().cpu() for p in phase_x_layers],
        "phase_y_layers": [p.detach().cpu() for p in phase_y_layers],
        "loss_history": losses,
        "oracle_backend": "slmsuite_dual_seed+torchoptics_finetune",
    }
