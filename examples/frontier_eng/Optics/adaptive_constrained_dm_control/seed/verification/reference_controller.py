import numpy as np
from scipy.optimize import lsq_linear


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.15,
) -> np.ndarray:
    """
    Reference (third-party oracle): bounded least squares from SciPy.

    Solves:
        min_u ||H u - s||^2 + beta ||u||^2
        s.t.  -V <= u_i <= V

    via scipy.optimize.lsq_linear on an augmented system.
    """
    a_aug = control_model["ridge_design_matrix"]
    rhs_tail = control_model["ridge_rhs_zeros"]
    lag_comp_gain = float(control_model.get("lag_comp_gain", 0.0))
    h_matrix = control_model.get("h_matrix")
    if prev_commands is not None and h_matrix is not None and lag_comp_gain > 0.0:
        # Delay compensation with nominal slope prediction from previous applied command.
        slopes = slopes + lag_comp_gain * (h_matrix @ prev_commands)

    b_aug = np.concatenate([slopes, rhs_tail])

    result = lsq_linear(
        a_aug,
        b_aug,
        bounds=(-max_voltage, max_voltage),
        method="trf",
        lsmr_tol="auto",
        max_iter=400,
    )
    return result.x.astype(np.float64, copy=False)
