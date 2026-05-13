# EVOLVE-BLOCK-START
import math
import torch
import torch.nn.functional as F
from .task import Config, input_t, output_t


def custom_kernel(data: input_t) -> output_t:
    """Naive attention implementation. ALLOWED TO MODIFY."""
    config, Q, K, V = data

    # Naive: materialize full attention matrix
    scores = torch.matmul(Q, K.transpose(-1, -2)) * config.scale

    if config.causal:
        seq_len_q = Q.size(-2)
        seq_len_kv = K.size(-2)
        # Causal mask: position i can attend to positions 0..i
        mask = torch.triu(
            torch.full((seq_len_q, seq_len_kv), float('-inf'), device=Q.device, dtype=Q.dtype),
            diagonal=seq_len_kv - seq_len_q + 1,
        )
        scores = scores + mask

    attn = torch.softmax(scores, dim=-1).to(Q.dtype)
    output = torch.matmul(attn, V)
    return output
# EVOLVE-BLOCK-END
