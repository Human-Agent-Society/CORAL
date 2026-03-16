"""CORAL Web Dashboard — Starlette app serving React UI + JSON API."""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette

from coral.web.app import create_app

__all__ = ["create_app"]
