"""Tests for YAML configuration."""

import tempfile
from pathlib import Path

from coral.config import AgentConfig, CoralConfig, GraderConfig, TaskConfig


def test_config_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test", files=["main.py"], tips="Be fast"),
        grader=GraderConfig(type="function", module="my_module", args={"k": 1}),
        agents=AgentConfig(count=2, model="opus"),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.task.name == "test"
    assert restored.task.files == ["main.py"]
    assert restored.grader.type == "function"
    assert restored.agents.count == 2
    assert restored.agents.model == "opus"


def test_config_from_dict():
    data = {
        "task": {"name": "t", "description": "d"},
        "grader": {"type": "kernel_builder"},
    }
    config = CoralConfig.from_dict(data)
    assert config.task.name == "t"
    assert config.grader.type == "kernel_builder"
    assert config.agents.count == 1  # default
