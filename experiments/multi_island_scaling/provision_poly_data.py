#!/usr/bin/env python3
"""Provision only the public Frontier-CS #0 data inside the grader private dir."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from scaling_poly_grader.constants import (
    FRONTIER_COMMIT,
    FRONTIER_REPOSITORY,
    PRIVATE_CHECKOUT_NAME,
)


def main() -> None:
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if not virtual_env:
        raise SystemExit("VIRTUAL_ENV is required while setting up the grader")
    private_dir = Path(virtual_env).parent
    target = private_dir / PRIVATE_CHECKOUT_NAME
    expected_problem = target / "algorithmic" / "problems" / "0" / "testdata"
    if expected_problem.is_dir() and any(expected_problem.glob("*.in")):
        return

    with tempfile.TemporaryDirectory(prefix="frontier-cs-", dir=private_dir) as temp:
        checkout = Path(temp) / "checkout"
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(
            ["git", "-C", str(checkout), "remote", "add", "origin", FRONTIER_REPOSITORY], check=True
        )
        sparse_file = checkout / ".git" / "info" / "sparse-checkout"
        sparse_file.parent.mkdir(parents=True, exist_ok=True)
        sparse_file.write_text("algorithmic/problems/0\nalgorithmic/judge/include\n")
        subprocess.run(
            ["git", "-C", str(checkout), "config", "core.sparseCheckout", "true"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(checkout), "fetch", "--depth", "1", "origin", FRONTIER_COMMIT],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(checkout), "checkout", "-q", "--detach", "FETCH_HEAD"],
            check=True,
        )
        # Keep only the public files needed by the evaluator.  The sparse
        # checkout's Git pack can still contain unrelated repository blobs;
        # retaining it would waste hundreds of megabytes in every cell.
        shutil.rmtree(checkout / ".git")
        if target.exists():
            raise SystemExit(f"unexpected incomplete private checkout already exists: {target}")
        checkout.rename(target)


if __name__ == "__main__":
    main()
