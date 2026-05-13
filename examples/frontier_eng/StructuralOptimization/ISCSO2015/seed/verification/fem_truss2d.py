"""
2D Truss Finite Element Method (FEM) Solver

Implements the Direct Stiffness Method for planar truss structures.
All units are assumed consistent (mm, N, MPa system).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def compute_element_stiffness(
    xi: float, yi: float, xj: float, yj: float, E: float, A: float
) -> tuple[NDArray, float]:
    """
    Compute the 4x4 element stiffness matrix for a 2D truss element.

    Parameters
    ----------
    xi, yi : float
        Coordinates of node i.
    xj, yj : float
        Coordinates of node j.
    E : float
        Elastic modulus (MPa).
    A : float
        Cross-sectional area (mm^2).

    Returns
    -------
    ke : ndarray, shape (4, 4)
        Element stiffness matrix in global coordinates.
    L : float
        Element length (mm).
    """
    dx = xj - xi
    dy = yj - yi
    L = np.sqrt(dx * dx + dy * dy)
    if L < 1e-12:
        raise ValueError(f"Degenerate element: zero length (dx={dx}, dy={dy})")

    c = dx / L  # cos(theta)
    s = dy / L  # sin(theta)

    coeff = E * A / L
    ke = coeff * np.array(
        [
            [c * c, c * s, -c * c, -c * s],
            [c * s, s * s, -c * s, -s * s],
            [-c * c, -c * s, c * c, c * s],
            [-c * s, -s * s, c * s, s * s],
        ]
    )
    return ke, L


def compute_element_stress(
    xi: float,
    yi: float,
    xj: float,
    yj: float,
    E: float,
    u_elem: NDArray,
) -> tuple[float, float]:
    """
    Compute axial stress in a 2D truss element.

    Parameters
    ----------
    xi, yi, xj, yj : float
        Node coordinates.
    E : float
        Elastic modulus.
    u_elem : ndarray, shape (4,)
        Element displacement vector [u_ix, u_iy, u_jx, u_jy].

    Returns
    -------
    stress : float
        Axial stress (positive = tension, negative = compression).
    L : float
        Element length.
    """
    dx = xj - xi
    dy = yj - yi
    L = np.sqrt(dx * dx + dy * dy)
    if L < 1e-12:
        raise ValueError("Degenerate element: zero length")

    c = dx / L
    s = dy / L

    # Axial strain = (u_j - u_i) . e / L, where e = (c, s)
    strain = (-c * u_elem[0] - s * u_elem[1] + c * u_elem[2] + s * u_elem[3]) / L
    stress = E * strain
    return stress, L


class TrussFEM2D:
    """
    2D Truss FEM solver using the Direct Stiffness Method.

    Parameters
    ----------
    nodes : ndarray, shape (n_nodes, 2)
        Node coordinates [x, y] in mm.
    elements : ndarray, shape (n_elements, 2)
        Element connectivity [node_i, node_j], 0-indexed.
    E : float
        Elastic modulus (MPa).
    supports : list of dict
        Each dict has 'node', 'fix_x', 'fix_y'.
    """

    def __init__(
        self,
        nodes: NDArray,
        elements: NDArray,
        E: float,
        supports: list[dict],
    ):
        self.nodes = np.array(nodes, dtype=float)
        self.elements = np.array(elements, dtype=int)
        self.E = E
        self.supports = supports
        self.n_nodes = len(self.nodes)
        self.n_elements = len(self.elements)
        self.n_dofs = 2 * self.n_nodes

        # Build fixed DOF set (convert 1-based node IDs to 0-based DOF indices)
        self.fixed_dofs: set[int] = set()
        for sup in self.supports:
            nid = sup["node"]
            idx = nid - 1
            if sup.get("fix_x", False):
                self.fixed_dofs.add(2 * idx)
            if sup.get("fix_y", False):
                self.fixed_dofs.add(2 * idx + 1)

        self.free_dofs = sorted(set(range(self.n_dofs)) - self.fixed_dofs)
        self.free_dof_index = {dof: idx for idx, dof in enumerate(self.free_dofs)}

    def solve(
        self, areas: NDArray, forces: NDArray
    ) -> tuple[NDArray, NDArray, NDArray]:
        """
        Solve the truss FEM problem for given areas and load vector.

        Parameters
        ----------
        areas : ndarray, shape (n_elements,)
            Cross-sectional areas (mm^2).
        forces : ndarray, shape (n_dofs,) or (n_nodes, 2)
            Applied force vector. If shape (n_nodes, 2), it is flattened.

        Returns
        -------
        displacements : ndarray, shape (n_dofs,)
            Global displacement vector (mm). Fixed DOFs are zero.
        stresses : ndarray, shape (n_elements,)
            Axial stress in each element (MPa).
        lengths : ndarray, shape (n_elements,)
            Length of each element (mm).
        """
        if forces.ndim == 2:
            forces = forces.flatten()

        n_free = len(self.free_dofs)
        K_red = np.zeros((n_free, n_free))
        lengths = np.zeros(self.n_elements)

        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi, yi = self.nodes[ni]
            xj, yj = self.nodes[nj]
            A = areas[e]

            ke, L = compute_element_stiffness(xi, yi, xj, yj, self.E, A)
            lengths[e] = L

            # Global DOF indices for this element
            dofs_e = [2 * ni, 2 * ni + 1, 2 * nj, 2 * nj + 1]

            # Assemble into reduced system
            for i_local, dof_i in enumerate(dofs_e):
                if dof_i not in self.free_dof_index:
                    continue
                ii = self.free_dof_index[dof_i]
                for j_local, dof_j in enumerate(dofs_e):
                    if dof_j not in self.free_dof_index:
                        continue
                    jj = self.free_dof_index[dof_j]
                    K_red[ii, jj] += ke[i_local, j_local]

        # Reduced force vector
        F_red = forces[self.free_dofs]

        # Check conditioning
        cond = np.linalg.cond(K_red)
        if cond > 1e15:
            raise ValueError(
                f"Stiffness matrix is ill-conditioned (cond={cond:.2e}). "
                "Check for mechanism or degenerate elements."
            )

        # Solve
        u_red = np.linalg.solve(K_red, F_red)

        # Reconstruct full displacement vector
        displacements = np.zeros(self.n_dofs)
        for idx, dof in enumerate(self.free_dofs):
            displacements[dof] = u_red[idx]

        # Compute element stresses
        stresses = np.zeros(self.n_elements)
        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi, yi = self.nodes[ni]
            xj, yj = self.nodes[nj]
            u_elem = np.array(
                [
                    displacements[2 * ni],
                    displacements[2 * ni + 1],
                    displacements[2 * nj],
                    displacements[2 * nj + 1],
                ]
            )
            stresses[e], _ = compute_element_stress(xi, yi, xj, yj, self.E, u_elem)

        return displacements, stresses, lengths

    def compute_weight(self, areas: NDArray, rho: float) -> float:
        """
        Compute total structural weight.

        Parameters
        ----------
        areas : ndarray, shape (n_elements,)
            Cross-sectional areas (mm^2).
        rho : float
            Material density (kg/mm^3).

        Returns
        -------
        weight : float
            Total weight (kg).
        """
        weight = 0.0
        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi, yi = self.nodes[ni]
            xj, yj = self.nodes[nj]
            dx = xj - xi
            dy = yj - yi
            L = np.sqrt(dx * dx + dy * dy)
            weight += rho * L * areas[e]
        return weight

