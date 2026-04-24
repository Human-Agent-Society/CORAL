"""Local ``RubricItem`` — mirrors the shape used by the grader without
pulling anything extra from ``coral.config``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RubricItem:
    name: str
    description: str = ""
    weight: float = 1.0
