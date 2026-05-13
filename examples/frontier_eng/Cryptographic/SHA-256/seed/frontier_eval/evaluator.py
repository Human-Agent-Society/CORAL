from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from evaluator_impl import evaluate as _evaluate
from spec import (
    CRYPTO_AES128_SPEC,
    CRYPTO_SHA256_SPEC,
    CRYPTO_SHA3_256_SPEC,
)

_SPEC_BY_BENCHMARK = {
    "AES-128": CRYPTO_AES128_SPEC,
    "SHA-256": CRYPTO_SHA256_SPEC,
    "SHA3-256": CRYPTO_SHA3_256_SPEC,
}


def _flag_from_env(name: str) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_benchmark_name() -> str:
    env_candidates = (
        os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", ""),
        os.environ.get("FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR", ""),
    )
    for raw in env_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        benchmark_name = Path(text).expanduser().resolve().name
        if benchmark_name in _SPEC_BY_BENCHMARK:
            return benchmark_name

    benchmark_name = Path(__file__).resolve().parents[1].name
    if benchmark_name in _SPEC_BY_BENCHMARK:
        return benchmark_name

    raise KeyError(
        "Unable to resolve cryptographic benchmark name from "
        f"FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR={env_candidates[0]!r}, "
        f"FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR={env_candidates[1]!r}, "
        f"local_path={Path(__file__).resolve()}"
    )


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    benchmark_name = _resolve_benchmark_name()
    spec = _SPEC_BY_BENCHMARK[benchmark_name]
    return _evaluate(
        program_path,
        repo_root=repo_root,
        spec=spec,
        include_pdf_reference=_flag_from_env(
            "FRONTIER_EVAL_UNIFIED_CRYPTO_INCLUDE_PDF_REFERENCE"
        ),
    )
