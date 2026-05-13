# EVOLVE-BLOCK-START
import torch
from dataclasses import dataclass
from typing import TypeVar, TypedDict


@dataclass
class Config:
    batch_size: int
    n_heads: int
    seq_len_q: int
    seq_len_kv: int
    head_dim: int
    causal: bool
    scale: float


input_t = TypeVar("input_t", bound=tuple[Config, torch.Tensor, torch.Tensor, torch.Tensor])
output_t = TypeVar("output_t", bound=torch.Tensor)


class TestSpec(TypedDict):
    batchsize: int
    nheads: int
    seqlen_q: int
    seqlen_kv: int
    headdim: int
    causal: int
    seed: int
# EVOLVE-BLOCK-END
