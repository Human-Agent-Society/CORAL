# EVOLVE-BLOCK-START
import math
import torch
import torch.nn.functional as F
from .task import Config, input_t, output_t
from .utils import make_match_reference


def generate_input(batchsize, nheads, seqlen_q, seqlen_kv, headdim, causal, seed):
    """Generate random Q, K, V tensors and config for flash attention."""
    gen = torch.Generator(device='cuda')
    gen.manual_seed(seed)

    config = Config(
        batch_size=batchsize,
        n_heads=nheads,
        seq_len_q=seqlen_q,
        seq_len_kv=seqlen_kv,
        head_dim=headdim,
        causal=bool(causal),
        scale=1.0 / math.sqrt(headdim),
    )

    # Q: (batch_size, n_heads, seq_len_q, head_dim)
    Q = torch.randn(
        (batchsize, nheads, seqlen_q, headdim),
        dtype=torch.bfloat16, generator=gen, device='cuda'
    ) * 0.1
    # K: (batch_size, n_heads, seq_len_kv, head_dim)
    K = torch.randn(
        (batchsize, nheads, seqlen_kv, headdim),
        dtype=torch.bfloat16, generator=gen, device='cuda'
    ) * 0.1
    # V: (batch_size, n_heads, seq_len_kv, head_dim)
    V = torch.randn(
        (batchsize, nheads, seqlen_kv, headdim),
        dtype=torch.bfloat16, generator=gen, device='cuda'
    ) * 0.1

    return config, Q, K, V


def ref_kernel(data: input_t) -> output_t:
    """Reference attention implementation using PyTorch scaled_dot_product_attention."""
    config, Q, K, V = data
    output = F.scaled_dot_product_attention(
        Q, K, V,
        attn_mask=None,
        is_causal=config.causal,
        scale=config.scale,
    )
    return output


check_implementation = make_match_reference(ref_kernel, rtol=2e-02, atol=8e-03)
# EVOLVE-BLOCK-END
