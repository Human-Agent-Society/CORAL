# EVOLVE-BLOCK-START
"""Baseline solver for Task 4: polarization-multiplexed focusing."""

from __future__ import annotations

from typing import Any

import torch
from torch.nn import Parameter

import torchoptics
from torchoptics import Field
from torchoptics.profiles import gaussian


def make_default_spec() -> dict[str, Any]:
    waist = 90e-6
    return {
        "shape": 40,
        "spacing": 10e-6,
        "wavelength": 700e-9,
        "waist_radius": waist,
        "layer_z": [0.08, 0.20],
        "output_z": 0.54,
        "pattern_x_centers": [(-1.9 * waist, -1.3 * waist), (0.0, 0.0), (1.9 * waist, 1.3 * waist)],
        "pattern_x_ratios": [0.50, 0.30, 0.20],
        "pattern_y_centers": [(-1.9 * waist, 1.3 * waist), (0.0, 0.0), (1.9 * waist, -1.3 * waist)],
        "pattern_y_ratios": [0.25, 0.35, 0.40],
        "steps": 40,
        "lr": 0.045,
    }


def _build_input_fields(spec: dict[str, Any], device: str) -> tuple[Field, Field]:
    shape = int(spec["shape"])
    base = gaussian(shape, spec["waist_radius"])  # real-valued profile

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


def solve(spec: dict[str, Any] | None = None, device: str | None = None, seed: int = 0) -> dict[str, Any]:
    spec = {**make_default_spec(), **(spec or {})}
    torch.manual_seed(seed)

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

    phase_x_layers = [Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device)) for _ in spec["layer_z"]]
    phase_y_layers = [Parameter(torch.zeros((shape, shape), dtype=torch.double, device=device)) for _ in spec["layer_z"]]

    optimizer = torch.optim.Adam([*phase_x_layers, *phase_y_layers], lr=float(spec["lr"]))
    losses: list[float] = []

    for _ in range(int(spec["steps"])):
        optimizer.zero_grad()

        out_x = _forward(field_x, spec, phase_x_layers, phase_y_layers)
        out_y = _forward(field_y, spec, phase_x_layers, phase_y_layers)

        map_x = out_x.intensity().sum(dim=-3)
        map_y = out_y.intensity().sum(dim=-3)

        map_x = map_x / (map_x.sum() + 1e-12)
        map_y = map_y / (map_y.sum() + 1e-12)

        loss = torch.mean((map_x - target_x) ** 2) + torch.mean((map_y - target_y) ** 2)
        loss.backward()
        optimizer.step()

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
    }
# EVOLVE-BLOCK-END
