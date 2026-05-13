"""
3D Truss Finite Element Method (FEM) Solver

Implements the Direct Stiffness Method for 3D space truss structures.
All units are assumed consistent (mm, N, MPa system).

Also includes the parametric tower topology generator for ISCSO 2023.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from scipy.sparse.linalg import spsolve


# ======================== Topology Generator ========================


def generate_tower_topology(
    num_levels: int = 23,
    total_height: float = 40000.0,
    bottom_half_width: float = 2000.0,
    top_half_width: float = 500.0,
    cross_bracing_levels: list[int] | None = None,
) -> tuple[NDArray, NDArray]:
    """
    Generate the node coordinates and element connectivity for a
    tapered 3D tower truss.

    Parameters
    ----------
    num_levels : int
        Number of levels (including bottom and top).
    total_height : float
        Total height of the tower (mm).
    bottom_half_width : float
        Half-width of the square cross-section at the base (mm).
    top_half_width : float
        Half-width at the top (mm).
    cross_bracing_levels : list of int, optional
        Levels at which floor cross-bracing is added.

    Returns
    -------
    nodes : ndarray, shape (num_levels * 4, 3)
        Node coordinates [x, y, z].
    elements : ndarray, shape (n_elements, 2)
        Element connectivity [node_i, node_j].
    """
    if cross_bracing_levels is None:
        cross_bracing_levels = [1, 4, 7, 10, 13, 16, 19, 22]

    n_nodes = num_levels * 4
    nodes = np.zeros((n_nodes, 3))

    for i in range(num_levels):
        t = i / (num_levels - 1)
        hw = bottom_half_width + t * (top_half_width - bottom_half_width)
        z = t * total_height

        base = 4 * i
        # Node ordering at each level: (+hw, +hw), (-hw, +hw), (-hw, -hw), (+hw, -hw)
        nodes[base + 0] = [+hw, +hw, z]
        nodes[base + 1] = [-hw, +hw, z]
        nodes[base + 2] = [-hw, -hw, z]
        nodes[base + 3] = [+hw, -hw, z]

    elements_list: list[tuple[int, int]] = []

    # Vertical columns (between adjacent levels)
    for i in range(num_levels - 1):
        for j in range(4):
            elements_list.append((4 * i + j, 4 * (i + 1) + j))

    # Horizontal perimeter bars (at each level)
    for i in range(num_levels):
        base = 4 * i
        elements_list.append((base + 0, base + 1))
        elements_list.append((base + 1, base + 2))
        elements_list.append((base + 2, base + 3))
        elements_list.append((base + 3, base + 0))

    # Face diagonals (one per face per bay)
    for i in range(num_levels - 1):
        # Face 0 (front, +y): node 0 of level i -> node 1 of level i+1
        elements_list.append((4 * i + 0, 4 * (i + 1) + 1))
        # Face 1 (left, -x): node 1 of level i -> node 2 of level i+1
        elements_list.append((4 * i + 1, 4 * (i + 1) + 2))
        # Face 2 (back, -y): node 2 of level i -> node 3 of level i+1
        elements_list.append((4 * i + 2, 4 * (i + 1) + 3))
        # Face 3 (right, +x): node 3 of level i -> node 0 of level i+1
        elements_list.append((4 * i + 3, 4 * (i + 1) + 0))

    # Floor cross-diagonals at selected levels
    for i in cross_bracing_levels:
        if i < num_levels:
            base = 4 * i
            elements_list.append((base + 0, base + 2))  # diagonal 1
            elements_list.append((base + 1, base + 3))  # diagonal 2

    elements = np.array(elements_list, dtype=int)
    return nodes, elements


# ======================== FEM Solver ========================


def compute_element_stiffness_3d(
    xi: NDArray,
    xj: NDArray,
    E: float,
    A: float,
) -> tuple[NDArray, float]:
    """
    Compute the 6x6 element stiffness matrix for a 3D truss element.

    Parameters
    ----------
    xi : ndarray, shape (3,)
        Coordinates of node i [x, y, z].
    xj : ndarray, shape (3,)
        Coordinates of node j [x, y, z].
    E : float
        Elastic modulus (MPa).
    A : float
        Cross-sectional area (mm^2).

    Returns
    -------
    ke : ndarray, shape (6, 6)
        Element stiffness matrix in global coordinates.
    L : float
        Element length (mm).
    """
    d = xj - xi
    L = np.linalg.norm(d)
    if L < 1e-12:
        raise ValueError(f"Degenerate element: zero length")

    # Direction cosines
    dc = d / L  # [l, m, n]

    # Outer product of direction cosines
    B = np.outer(dc, dc)  # 3x3

    coeff = E * A / L
    ke = coeff * np.block([[B, -B], [-B, B]])  # 6x6
    return ke, L


def compute_element_stress_3d(
    xi: NDArray,
    xj: NDArray,
    E: float,
    u_elem: NDArray,
) -> tuple[float, float]:
    """
    Compute axial stress in a 3D truss element.

    Parameters
    ----------
    xi, xj : ndarray, shape (3,)
        Node coordinates.
    E : float
        Elastic modulus.
    u_elem : ndarray, shape (6,)
        Element displacement vector [u_ix, u_iy, u_iz, u_jx, u_jy, u_jz].

    Returns
    -------
    stress : float
        Axial stress (positive = tension, negative = compression).
    L : float
        Element length.
    """
    d = xj - xi
    L = np.linalg.norm(d)
    if L < 1e-12:
        raise ValueError("Degenerate element: zero length")

    dc = d / L
    # Stress = E/L * [-l, -m, -n, l, m, n] . u
    T = np.array([-dc[0], -dc[1], -dc[2], dc[0], dc[1], dc[2]])
    stress = (E / L) * T.dot(u_elem)
    return stress, L


class TrussFEM3D:
    """
    3D Truss FEM solver using the Direct Stiffness Method with sparse matrices.

    Parameters
    ----------
    nodes : ndarray, shape (n_nodes, 3)
        Node coordinates [x, y, z] in mm.
    elements : ndarray, shape (n_elements, 2)
        Element connectivity [node_i, node_j], 0-indexed.
    E : float
        Elastic modulus (MPa).
    supports : list of dict
        Each dict has 'node', 'fix_x', 'fix_y', 'fix_z'.
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
        self.n_dofs = 3 * self.n_nodes

        # Build fixed DOF set
        self.fixed_dofs: set[int] = set()
        for sup in self.supports:
            nid = sup["node"]
            if sup.get("fix_x", False):
                self.fixed_dofs.add(3 * nid)
            if sup.get("fix_y", False):
                self.fixed_dofs.add(3 * nid + 1)
            if sup.get("fix_z", False):
                self.fixed_dofs.add(3 * nid + 2)

        self.free_dofs = sorted(set(range(self.n_dofs)) - self.fixed_dofs)
        self.free_dof_index = {dof: idx for idx, dof in enumerate(self.free_dofs)}

        # Precompute element lengths
        self.lengths = np.zeros(self.n_elements)
        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            d = self.nodes[nj] - self.nodes[ni]
            self.lengths[e] = np.linalg.norm(d)

    def solve(
        self, areas: NDArray, forces: NDArray
    ) -> tuple[NDArray, NDArray]:
        """
        Solve the 3D truss FEM problem for given areas and load vector.

        Parameters
        ----------
        areas : ndarray, shape (n_elements,)
            Cross-sectional areas (mm^2).
        forces : ndarray, shape (n_dofs,) or (n_nodes, 3)
            Applied force vector.

        Returns
        -------
        displacements : ndarray, shape (n_dofs,)
            Global displacement vector (mm). Fixed DOFs are zero.
        stresses : ndarray, shape (n_elements,)
            Axial stress in each element (MPa).
        """
        if forces.ndim == 2:
            forces = forces.flatten()

        n_free = len(self.free_dofs)

        # Build sparse stiffness matrix using COO format
        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []

        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi = self.nodes[ni]
            xj = self.nodes[nj]
            A = areas[e]

            ke, _ = compute_element_stiffness_3d(xi, xj, self.E, A)

            # Global DOF indices for this element
            dofs_e = [3 * ni, 3 * ni + 1, 3 * ni + 2, 3 * nj, 3 * nj + 1, 3 * nj + 2]

            for i_local in range(6):
                dof_i = dofs_e[i_local]
                if dof_i not in self.free_dof_index:
                    continue
                ii = self.free_dof_index[dof_i]
                for j_local in range(6):
                    dof_j = dofs_e[j_local]
                    if dof_j not in self.free_dof_index:
                        continue
                    jj = self.free_dof_index[dof_j]
                    rows.append(ii)
                    cols.append(jj)
                    vals.append(ke[i_local, j_local])

        K_sparse = sparse.coo_matrix(
            (vals, (rows, cols)), shape=(n_free, n_free)
        ).tocsc()

        F_red = forces[self.free_dofs]

        # Solve sparse system
        u_red = spsolve(K_sparse, F_red)

        if not np.all(np.isfinite(u_red)):
            raise ValueError(
                "FEM solve produced non-finite displacements. "
                "Check for mechanism or ill-conditioning."
            )

        # Reconstruct full displacement vector
        displacements = np.zeros(self.n_dofs)
        for idx, dof in enumerate(self.free_dofs):
            displacements[dof] = u_red[idx]

        # Compute element stresses
        stresses = np.zeros(self.n_elements)
        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi = self.nodes[ni]
            xj = self.nodes[nj]
            u_elem = np.array([
                displacements[3 * ni],
                displacements[3 * ni + 1],
                displacements[3 * ni + 2],
                displacements[3 * nj],
                displacements[3 * nj + 1],
                displacements[3 * nj + 2],
            ])
            stresses[e], _ = compute_element_stress_3d(xi, xj, self.E, u_elem)

        return displacements, stresses

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
        return float(np.sum(rho * self.lengths * areas))

