"""Pinned public Frontier-CS checkout used by the experiment."""

from __future__ import annotations

from pathlib import Path

FRONTIER_REPOSITORY = "https://github.com/FrontierCS/Frontier-CS.git"
FRONTIER_COMMIT = "e8b6e3d210a14163ac32ebae52fa0ac065f124db"
PRIVATE_CHECKOUT_NAME = f"frontier-cs-{FRONTIER_COMMIT[:12]}"


def checkout_path(private_dir: str | Path) -> Path:
    """Return the private checkout path without exposing it in task args."""

    return Path(private_dir) / PRIVATE_CHECKOUT_NAME
