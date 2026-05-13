import numpy as np


def fuse_and_compute_dm_commands(
    slopes_multi: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.50,
) -> np.ndarray:
    """
    Reference (third-party oracle): anomaly-score weighted fusion.

    An IsolationForest (trained on clean slopes in evaluate.py) provides
    per-sensor normality scores. We keep top-scoring sensors and fuse them
    with softmax-like weights.
    """
    model = control_model.get("anomaly_model")
    inlier_fraction = float(control_model.get("inlier_fraction", 0.6))
    score_temperature = float(control_model.get("score_temperature", 0.08))
    h_matrix = control_model.get("h_matrix")
    delay_comp_gain = float(control_model.get("delay_comp_gain", 0.0))
    temporal_blend = float(control_model.get("temporal_blend", 0.0))

    if model is None or slopes_multi.shape[0] < 2:
        fused = np.median(slopes_multi, axis=0)
    else:
        score = model.decision_function(slopes_multi)
        n_keep = max(1, int(np.ceil(inlier_fraction * slopes_multi.shape[0])))
        keep_idx = np.argsort(score)[-n_keep:]

        score_kept = score[keep_idx]
        score_kept = score_kept - np.max(score_kept)
        w = np.exp(score_kept / (score_temperature + 1e-12))
        w = w / (np.sum(w) + 1e-12)
        fused = np.sum(slopes_multi[keep_idx] * w[:, None], axis=0)

    if prev_commands is not None and h_matrix is not None and delay_comp_gain > 0.0:
        fused = fused + delay_comp_gain * (h_matrix @ prev_commands)

    u = reconstructor @ fused
    if prev_commands is not None and temporal_blend > 0.0:
        u = (1.0 - temporal_blend) * u + temporal_blend * prev_commands
    return np.clip(u, -max_voltage, max_voltage)
