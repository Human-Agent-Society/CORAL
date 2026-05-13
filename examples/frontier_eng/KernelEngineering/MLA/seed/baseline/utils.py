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
    """Get the appropriate device (GPU or CPU)."""
    if use_cuda:
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif torch.backends.mps.is_available():
            return torch.device("mps")
        else:
            print("No compatible GPU found. Falling back to CPU.")
    return torch.device("cpu")


# Adapted from https://github.com/linkedin/Liger-Kernel/blob/main/test/utils.py
@torch.no_grad()
def verbose_allclose(
        received: torch.Tensor,
        expected: torch.Tensor,
        rtol=1e-05,
        atol=1e-08,
        max_print=5
) -> list[str]:
    """
    Assert that two tensors are element-wise equal within a tolerance, providing detailed information about mismatches.

    Parameters:
    received (torch.Tensor): Tensor we actually got.
    expected (torch.Tensor): Tensor we expected to receive.
    rtol (float): Relative tolerance; relative to expected
    atol (float): Absolute tolerance.
    max_print (int): Maximum number of mismatched elements to print.

    Raises:
    AssertionError: If the tensors are not all close within the given tolerance.
    """
    # Check if the shapes of the tensors match
    if received.shape != expected.shape:
        return [f"SIZE MISMATCH. received shape: {received.shape}, expected shape: {expected.shape}"]

    # Calculate the difference between the tensors
    diff = torch.abs(received - expected)

    # Determine the tolerance
    tolerance = atol + rtol * torch.abs(expected)

    # Find tolerance mismatched elements
    tol_mismatched = diff > tolerance

    # Find nan mismatched elements
    nan_mismatched = torch.logical_xor(torch.isnan(received), torch.isnan(expected))

    # Find +inf mismatched elements
    posinf_mismatched = torch.logical_xor(torch.isposinf(received), torch.isposinf(expected))
    # Find -inf mismatched elements
    neginf_mismatched = torch.logical_xor(torch.isneginf(received), torch.isneginf(expected))

    # Find all mismatched elements
    mismatched = torch.logical_or(
        torch.logical_or(tol_mismatched, nan_mismatched),
        torch.logical_or(posinf_mismatched, neginf_mismatched),
    )

    mismatched_indices = torch.nonzero(mismatched)

    # Count the number of mismatched elements
    num_mismatched = mismatched.count_nonzero().item()

    # Generate detailed information if there are mismatches
    if num_mismatched >= 1:
        mismatch_details = [f"Number of mismatched elements: {num_mismatched}"]

        for index in mismatched_indices[:max_print]:
            i = tuple(index.tolist())
            mismatch_details.append(f"ERROR AT {i}: {received[i]} {expected[i]}")
        if num_mismatched > max_print:
            mismatch_details.append(f"... and {num_mismatched - max_print} more mismatched elements.")
        return mismatch_details

    return []


@torch.no_grad()
def verbose_allequal(received: torch.Tensor, expected: torch.Tensor, max_print: int=5):
    """
    Assert that two tensors are element-wise perfectly equal, providing detailed information about mismatches.

    Parameters:
    received (torch.Tensor): Tensor we actually got.
    expected (torch.Tensor): Tensor we expected to receive.
    max_print (int): Maximum number of mismatched elements to print.

    Returns:
         Empty string if tensors are equal, otherwise detailed error information
    """
    mismatched = torch.not_equal(received, expected)
    mismatched_indices = torch.nonzero(mismatched)

    # Count the number of mismatched elements
    num_mismatched = mismatched.count_nonzero().item()

    # Generate detailed information if there are mismatches
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
    """
    Convenient "default" implementation for tasks' `check_implementation` function.
    """
    output_mla, output_kv = output

    # To fit in memory for the big test
    output_mla = output_mla.cpu()
    output_kv = output_kv.cpu()

    config, x, kv_cache = data
    expected_mla, expected_kv = reference((config, x, kv_cache))

    output_mla = output_mla.cuda()
    output_kv = output_kv.cuda()

    reasons_mla = verbose_allclose(output_mla, expected_mla, rtol=rtol, atol=atol)
    reasons_kv = verbose_allclose(output_kv, expected_kv, rtol=rtol, atol=atol)

    if len(reasons_mla) > 0:
        return "mismatch found on MLA output! custom implementation doesn't match reference: " + " ".join(reasons_mla)
    if len(reasons_kv) > 0:
        return "mismatch found on KV cache output! custom implementation doesn't match reference: " + " ".join(reasons_kv)

    return ''


def make_match_reference(reference: callable, **kwargs):
    def wrapped(data, output):
        return match_reference(data, output, reference=reference, **kwargs)
    return wrapped
# EVOLVE-BLOCK-END
