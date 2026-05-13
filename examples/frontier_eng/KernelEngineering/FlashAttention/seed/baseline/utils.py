# EVOLVE-BLOCK-START
import random
import numpy as np
import torch


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def get_device(use_cuda: bool = True) -> torch.device:
    if use_cuda:
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif torch.backends.mps.is_available():
            return torch.device("mps")
        else:
            print("No compatible GPU found. Falling back to CPU.")
    return torch.device("cpu")


@torch.no_grad()
def verbose_allclose(
        received: torch.Tensor,
        expected: torch.Tensor,
        rtol=1e-05,
        atol=1e-08,
        max_print=5
) -> list[str]:
    if received.shape != expected.shape:
        return [f"SIZE MISMATCH. received shape: {received.shape}, expected shape: {expected.shape}"]

    diff = torch.abs(received - expected)
    tolerance = atol + rtol * torch.abs(expected)
    tol_mismatched = diff > tolerance
    nan_mismatched = torch.logical_xor(torch.isnan(received), torch.isnan(expected))
    posinf_mismatched = torch.logical_xor(torch.isposinf(received), torch.isposinf(expected))
    neginf_mismatched = torch.logical_xor(torch.isneginf(received), torch.isneginf(expected))

    mismatched = torch.logical_or(
        torch.logical_or(tol_mismatched, nan_mismatched),
        torch.logical_or(posinf_mismatched, neginf_mismatched),
    )
    mismatched_indices = torch.nonzero(mismatched)
    num_mismatched = mismatched.count_nonzero().item()

    if num_mismatched >= 1:
        mismatch_details = [f"Number of mismatched elements: {num_mismatched}"]
        for index in mismatched_indices[:max_print]:
            i = tuple(index.tolist())
            mismatch_details.append(f"ERROR AT {i}: {received[i]} {expected[i]}")
        if num_mismatched > max_print:
            mismatch_details.append(f"... and {num_mismatched - max_print} more mismatched elements.")
        return mismatch_details

    return []


def match_reference(data, output, reference: callable, rtol=1e-05, atol=1e-08):
    expected = reference(data)
    reasons = verbose_allclose(output.cpu(), expected.cpu(), rtol=rtol, atol=atol)
    if len(reasons) > 0:
        return "mismatch found on attention output! custom implementation doesn't match reference: " + " ".join(reasons)
    return ''


def make_match_reference(reference: callable, **kwargs):
    def wrapped(data, output):
        return match_reference(data, output, reference=reference, **kwargs)
    return wrapped
# EVOLVE-BLOCK-END
