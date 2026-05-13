# EVOLVE-BLOCK-START
import numpy as np


def fuse_and_compute_dm_commands(
    slopes_multi: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.50,
) -> np.ndarray:
    """
    Baseline: naive average over all WFS channels.

    Sensitive to corrupted sensors.
    """
    fused = np.mean(slopes_multi, axis=0)
    u = reconstructor @ fused
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END
