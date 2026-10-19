"""Fixtures for the evolving-evaluation tests: a fresh on-disk harness per test."""

from __future__ import annotations

import pytest

from tests.evolution_harness import Harness, reset


@pytest.fixture(autouse=True)
def _clean():
    reset()
    yield
    reset()


@pytest.fixture
def h(tmp_path):
    return Harness(root=tmp_path)
