import numpy as np
from sklearn.linear_model import Lasso


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.35,
) -> np.ndarray:
    """
    Reference (third-party oracle): L1 control solved by scikit-learn Lasso.

    Objective form in Lasso:
        (1 / (2m)) * ||H u - s||^2 + alpha * ||u||_1
    then command box projection is enforced by clipping.
    """
    h = control_model["h_matrix"]
    alpha = float(control_model.get("lasso_alpha", 5e-4))
    max_iter = int(control_model.get("lasso_max_iter", 2500))
    tol = float(control_model.get("lasso_tol", 1e-5))
    delay_comp_gain = float(control_model.get("delay_comp_gain", 0.0))
    temporal_blend = float(control_model.get("temporal_blend", 0.0))

    if prev_commands is not None and delay_comp_gain > 0.0:
        # Predict current slopes from previous applied command for delayed-WFS setting.
        slopes = slopes + delay_comp_gain * (h @ prev_commands)

    model = Lasso(alpha=alpha, fit_intercept=False, max_iter=max_iter, tol=tol)
    model.fit(h, slopes)

    u = np.asarray(model.coef_, dtype=np.float64)
    if prev_commands is not None and temporal_blend > 0.0:
        u = (1.0 - temporal_blend) * u + temporal_blend * prev_commands
    return np.clip(u, -max_voltage, max_voltage)
