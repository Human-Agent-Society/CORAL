"""Tests for lift-guided meta-evolve attribution and selection."""

from __future__ import annotations

import subprocess
import sys

import pytest

from coral.agent.meta_evolve import (
    MetaEvolveAttribution,
    attempt_attribution,
    attribution_metadata,
    validate_attribution,
)
from coral.config import MetaEvolveArmConfig, MetaEvolveConfig
from coral.types import Attempt


def _enabled_config() -> MetaEvolveConfig:
    return MetaEvolveConfig(
        enabled=True,
        arms=[
            MetaEvolveArmConfig(operator="prompt", mutation="rewrite"),
            MetaEvolveArmConfig(operator="implementation", mutation="replace"),
        ],
    )


def _attempt(metadata: dict) -> Attempt:
    return Attempt(
        commit_hash="a" * 40,
        agent_id="agent-1",
        title="test attempt",
        score=2.0,
        status="improved",
        parent_hash="b" * 40,
        timestamp="2026-08-29T00:00:00+00:00",
        metadata=metadata,
    )


def test_validate_attribution_requires_paired_values():
    with pytest.raises(ValueError, match="together"):
        validate_attribution(
            MetaEvolveConfig(),
            operator="prompt",
            mutation=None,
            tune=False,
        )


def test_validate_attribution_requires_configured_arm_when_enabled():
    with pytest.raises(ValueError, match="configured arm"):
        validate_attribution(
            _enabled_config(),
            operator="prompt",
            mutation="unknown",
            tune=False,
        )


def test_validate_attribution_requires_real_attempt_tag_when_enabled():
    with pytest.raises(ValueError, match="requires --operator and --mutation"):
        validate_attribution(
            _enabled_config(),
            operator=None,
            mutation=None,
            tune=False,
        )


def test_validate_attribution_allows_untagged_tune_attempt():
    assert (
        validate_attribution(
            _enabled_config(),
            operator=None,
            mutation=None,
            tune=True,
        )
        is None
    )


def test_validate_attribution_normalizes_values():
    assert validate_attribution(
        _enabled_config(),
        operator=" prompt ",
        mutation=" rewrite ",
        tune=False,
    ) == MetaEvolveAttribution(operator="prompt", mutation="rewrite")


def test_validate_attribution_accepts_explicit_disabled_run_labels():
    assert validate_attribution(
        MetaEvolveConfig(),
        operator="research",
        mutation="literature-search",
        tune=False,
    ) == MetaEvolveAttribution(operator="research", mutation="literature-search")


def test_attempt_attribution_reads_nested_metadata():
    attempt = _attempt({"meta_evolve": {"operator": "prompt", "mutation": "rewrite"}})

    assert attempt_attribution(attempt) == MetaEvolveAttribution(
        operator="prompt",
        mutation="rewrite",
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"meta_evolve": "prompt/rewrite"},
        {"meta_evolve": {"operator": "prompt"}},
        {"meta_evolve": {"operator": " ", "mutation": "rewrite"}},
    ],
)
def test_attempt_attribution_ignores_missing_or_malformed_metadata(metadata):
    assert attempt_attribution(_attempt(metadata)) is None


def test_attribution_metadata_uses_nested_namespaced_shape():
    attribution = MetaEvolveAttribution(operator="prompt", mutation="rewrite")

    assert attribution_metadata(attribution) == {
        "meta_evolve": {"operator": "prompt", "mutation": "rewrite"}
    }


def test_eval_help_documents_meta_evolve_attribution():
    result = subprocess.run(
        [sys.executable, "-m", "coral.cli", "eval", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "--operator" in result.stdout
    assert "--mutation" in result.stdout
