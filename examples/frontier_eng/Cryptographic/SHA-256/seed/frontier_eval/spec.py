from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CryptographicSpec:
    benchmark_subdir: str
    baseline_source: str
    custom_binary: str
    reference_pdf: str

    def benchmark_dir(self, repo_root: Path) -> Path:
        return (repo_root / "benchmarks" / "Cryptographic" / self.benchmark_subdir).resolve()


CRYPTO_AES128_SPEC = CryptographicSpec(
    benchmark_subdir="AES-128",
    baseline_source="AES-128.cpp",
    custom_binary="custom_aes",
    reference_pdf="AES.pdf",
)

CRYPTO_SHA256_SPEC = CryptographicSpec(
    benchmark_subdir="SHA-256",
    baseline_source="SHA-256.cpp",
    custom_binary="custom_sha",
    reference_pdf="SHA-256.pdf",
)

CRYPTO_SHA3_256_SPEC = CryptographicSpec(
    benchmark_subdir="SHA3-256",
    baseline_source="SHA3-256.cpp",
    custom_binary="custom_sha3",
    reference_pdf="SHA3-256.pdf",
)

