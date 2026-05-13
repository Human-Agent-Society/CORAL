# EVOLVE-BLOCK-START
"""
PyMOTOSIMPCompliance baseline candidate (portable NumPy-only implementation).

DO NOT MODIFY:
- load_problem()
- element_stiffness_matrix()
- fem_solve_dense()
- compliance_and_sensitivities()
- sensitivity_filter()
- output contract in main()

ALLOWED TO MODIFY:
- solve()
- oc_update() internals
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def load_problem() -> dict[str, Any]:
    """DO NOT MODIFY: load benchmark configuration."""
    candidates = [
        Path("references/problem_config.json"),
        Path(__file__).resolve().parent.parent / "references" / "problem_config.json",
    ]
    for p in candidates:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("problem_config.json not found")


def element_stiffness_matrix(nu: float) -> np.ndarray:
    """DO NOT MODIFY: Q4 element stiffness matrix for plane stress."""
    k = np.array(
        [
            0.5 - nu / 6.0,
            0.125 + nu / 8.0,
            -0.25 - nu / 12.0,
            -0.125 + 3.0 * nu / 8.0,
            -0.25 + nu / 12.0,
            -0.125 - nu / 8.0,
            nu / 6.0,
            0.125 - 3.0 * nu / 8.0,
        ],
        dtype=float,
    )
    ke = (1.0 / (1.0 - nu**2)) * np.array(
        [
            [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
            [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
            [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
            [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
            [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
            [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
            [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
            [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
        ],
        dtype=float,
    )
    return ke


def fem_solve_dense(nelx: int, nely: int, x: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    """DO NOT MODIFY: dense FEM solve for cantilever boundary/load setup."""
    e0 = float(cfg["E0"])
    emin = float(cfg["Emin"])
    penal = float(cfg["penal"])
    nu = float(cfg["nu"])
    force_mag = float(cfg.get("force_magnitude", -1.0))
    if abs(force_mag) < 1e-12:
        force_mag = -1.0

    ke = element_stiffness_matrix(nu)
    ndof = 2 * (nelx + 1) * (nely + 1)
    k_global = np.zeros((ndof, ndof), dtype=float)

    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array(
                [
                    2 * n1,
                    2 * n1 + 1,
                    2 * n2,
                    2 * n2 + 1,
                    2 * n2 + 2,
                    2 * n2 + 3,
                    2 * n1 + 2,
                    2 * n1 + 3,
                ],
                dtype=int,
            )
            ee = emin + (x[ely, elx] ** penal) * (e0 - emin)
            k_global[np.ix_(edof, edof)] += ee * ke

    f = np.zeros(ndof, dtype=float)
    load_node = nelx * (nely + 1) + (nely // 2)
    load_dof = 2 * load_node + int(cfg.get("force_direction", 1))
    f[load_dof] = force_mag

    fixed = []
    for j in range(nely + 1):
        node = j
        fixed.extend([2 * node, 2 * node + 1])
    fixed = np.array(sorted(set(fixed)), dtype=int)
    free = np.setdiff1d(np.arange(ndof, dtype=int), fixed)

    k_ff = k_global[np.ix_(free, free)]
    f_f = f[free]

    u = np.zeros(ndof, dtype=float)
    reg = 1e-9 * np.eye(k_ff.shape[0], dtype=float)
    u[free] = np.linalg.solve(k_ff + reg, f_f)
    return u


def compliance_and_sensitivities(
    nelx: int,
    nely: int,
    x: np.ndarray,
    u: np.ndarray,
    cfg: dict[str, Any],
) -> tuple[float, np.ndarray]:
    """DO NOT MODIFY: return compliance and element sensitivities."""
    e0 = float(cfg["E0"])
    emin = float(cfg["Emin"])
    penal = float(cfg["penal"])
    nu = float(cfg["nu"])

    ke = element_stiffness_matrix(nu)
    c = 0.0
    dc = np.zeros((nely, nelx), dtype=float)

    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array(
                [
                    2 * n1,
                    2 * n1 + 1,
                    2 * n2,
                    2 * n2 + 1,
                    2 * n2 + 2,
                    2 * n2 + 3,
                    2 * n1 + 2,
                    2 * n1 + 3,
                ],
                dtype=int,
            )
            ue = u[edof]
            ce = float(ue @ ke @ ue)
            ee = emin + (x[ely, elx] ** penal) * (e0 - emin)
            c += ee * ce
            dc[ely, elx] = -penal * (x[ely, elx] ** (penal - 1.0)) * (e0 - emin) * ce

    return float(c), dc


def sensitivity_filter(nelx: int, nely: int, rmin: float, x: np.ndarray, dc: np.ndarray) -> np.ndarray:
    """DO NOT MODIFY: mesh-independency sensitivity filter."""
    dcf = np.zeros_like(dc)
    radius = int(np.ceil(rmin))
    for i in range(nelx):
        for j in range(nely):
            s = 0.0
            num = 0.0
            for k in range(max(0, i - radius), min(nelx, i + radius + 1)):
                for l in range(max(0, j - radius), min(nely, j + radius + 1)):
                    fac = rmin - np.sqrt((i - k) ** 2 + (j - l) ** 2)
                    if fac > 0.0:
                        num += fac * x[l, k] * dc[l, k]
                        s += fac * x[l, k]
            dcf[j, i] = num / max(s, 1e-12)
    return dcf


def oc_update(
    x: np.ndarray,
    dc: np.ndarray,
    volfrac: float,
    move: float,
    rho_min: float,
) -> np.ndarray:
    """ALLOWED TO MODIFY: OC update with bisection on Lagrange multiplier."""
    l1, l2 = 0.0, 1e9
    while (l2 - l1) / max(1e-12, l1 + l2) > 1e-4:
        lmid = 0.5 * (l1 + l2)
        be = np.sqrt(np.maximum(1e-30, -dc / max(lmid, 1e-30)))
        x_new = np.maximum(
            rho_min,
            np.maximum(
                x - move,
                np.minimum(1.0, np.minimum(x + move, x * be)),
            ),
        )
        if float(np.mean(x_new)) > volfrac:
            l1 = lmid
        else:
            l2 = lmid
    return x_new


def solve() -> np.ndarray:
    """ALLOWED TO MODIFY: baseline SIMP+OC loop."""
    cfg = load_problem()
    nelx = int(cfg["nelx"])
    nely = int(cfg["nely"])
    volfrac = float(cfg["volfrac"])
    rmin = float(cfg["filter_radius"])
    move = float(cfg.get("move_limit", 0.2))
    rho_min = float(cfg.get("rho_min", 1e-9))
    max_iter = int(cfg.get("max_iter", 35))

    x = np.full((nely, nelx), volfrac, dtype=float)

    for _ in range(max_iter):
        u = fem_solve_dense(nelx, nely, x, cfg)
        _, dc = compliance_and_sensitivities(nelx, nely, x, u, cfg)
        dcf = sensitivity_filter(nelx, nely, rmin, x, dc)
        x_new = oc_update(x, dcf, volfrac, move, rho_min)

        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < 1e-3:
            break

    return np.clip(x, rho_min, 1.0)


def main() -> None:
    cfg = load_problem()
    x = solve()

    nelx = int(cfg["nelx"])
    nely = int(cfg["nely"])

    u = fem_solve_dense(nelx, nely, x, cfg)
    compliance, _ = compliance_and_sensitivities(nelx, nely, x, u, cfg)
    volume_fraction = float(np.mean(x))
    feasible = bool(volume_fraction <= float(cfg["volfrac"]) + 1e-6)

    submission = {
        "benchmark_id": str(cfg.get("benchmark_id", "pymoto_simp_compliance")),
        "nelx": nelx,
        "nely": nely,
        "density_vector": x.flatten().tolist(),
        "compliance": float(compliance),
        "volume_fraction": volume_fraction,
        "feasible": feasible,
    }

    out_dir = Path("temp")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "submission.json"
    out_path.write_text(json.dumps(submission, indent=2), encoding="utf-8")

    print(f"submission: {out_path}")
    print(f"compliance: {compliance:.6f}")
    print(f"volume_fraction: {volume_fraction:.6f}")
    print(f"feasible: {feasible}")


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
