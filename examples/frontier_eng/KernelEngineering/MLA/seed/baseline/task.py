# EVOLVE-BLOCK-START
import torch
from typing import TypeVar, TypedDict

input_t = TypeVar("input_t", bound=tuple[torch.nn.Module, torch.Tensor, torch.Tensor])
output_t = TypeVar("output_t", bound=tuple[torch.Tensor, torch.Tensor])

class TestSpec(TypedDict):
    batchsize: int
    dim: int
    dq: int
    prefill: int
    seed: int
# EVOLVE-BLOCK-END
