import numpy as np


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray,
    max_voltage: float = 0.25,
) -> np.ndarray:
    """
    Reference: temporally smooth controller.

    Solves (closed-form, then clipped):
        min_u ||H u - s||^2 + beta ||u - u_prev||^2
    """
    smooth_reconstructor = control_model["smooth_reconstructor"]
    prev_blend = control_model["prev_blend"]
    reconstructor_ff = control_model.get("reconstructor")
    delay_prediction_gain = float(control_model.get("delay_prediction_gain", 0.0))
    command_lowpass = float(control_model.get("command_lowpass", 0.0))

    u = smooth_reconstructor @ slopes + prev_blend @ prev_commands
    if reconstructor_ff is not None and delay_prediction_gain > 0.0:
        # Delay-aware feed-forward correction against stale WFS slopes.
        u += delay_prediction_gain * (reconstructor_ff @ slopes - prev_commands)
    if command_lowpass > 0.0:
        u = (1.0 - command_lowpass) * u + command_lowpass * prev_commands
    return np.clip(u, -max_voltage, max_voltage)
