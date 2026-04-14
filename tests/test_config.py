"""Tests for YAML configuration."""

import tempfile

import pytest

from coral.config import (
    AgentConfig,
    CoralConfig,
    GraderConfig,
    RunConfig,
    TaskConfig,
    WarmStartConfig,
    WorkspaceConfig,
)


def test_config_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test", tips="Be fast"),
        grader=GraderConfig(type="function", module="my_module", args={"k": 1}),
        agents=AgentConfig(count=2, model="opus"),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.task.name == "test"
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


def test_agent_runtime_options_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test"),
        agents=AgentConfig(
            runtime="codex",
            model="gpt-5.4",
            runtime_options={
                "model_reasoning_effort": "medium",
                "fast_mode": True,
            },
        ),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.agents.runtime_options == {
        "model_reasoning_effort": "medium",
        "fast_mode": True,
    }


def test_config_setup_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test"),
        workspace=WorkspaceConfig(
            setup=["pip install numpy", "python download_data.py"],
        ),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.workspace.setup == ["pip install numpy", "python download_data.py"]


def test_config_setup_defaults_empty():
    data = {
        "task": {"name": "t", "description": "d"},
    }
    config = CoralConfig.from_dict(data)
    assert config.workspace.setup == []


# --- OmegaConf-specific tests ---


def test_dotlist_merge():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test"),
        agents=AgentConfig(count=1, model="sonnet"),
    )
    merged = CoralConfig.merge_dotlist(config, ["agents.count=4", "agents.model=opus"])
    assert merged.agents.count == 4
    assert merged.agents.model == "opus"
    # Original unchanged
    assert config.agents.count == 1


def test_dotlist_merge_nested():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test"),
        grader=GraderConfig(timeout=300),
    )
    merged = CoralConfig.merge_dotlist(config, ["grader.timeout=600"])
    assert merged.grader.timeout == 600


def test_dotlist_merge_empty():
    config = CoralConfig(
        task=TaskConfig(name="test", description="A test"),
    )
    merged = CoralConfig.merge_dotlist(config, [])
    assert merged.task.name == "test"


def test_missing_required_field():
    """Missing task.name should raise an error."""
    from omegaconf.errors import MissingMandatoryValue

    with pytest.raises(MissingMandatoryValue):
        CoralConfig.from_dict({"task": {"description": "d"}})


def test_missing_task_description():
    from omegaconf.errors import MissingMandatoryValue

    with pytest.raises(MissingMandatoryValue):
        CoralConfig.from_dict({"task": {"name": "t"}})


def test_legacy_reflect_every():
    """Legacy reflect_every/heartbeat_every keys should be preprocessed."""
    data = {
        "task": {"name": "t", "description": "d"},
        "agents": {"reflect_every": 3, "heartbeat_every": 5},
    }
    config = CoralConfig.from_dict(data)
    assert config.agents.heartbeat_interval("reflect") == 3
    assert config.agents.heartbeat_interval("consolidate") == 5


def test_heartbeat_global_flag_roundtrip():
    """Heartbeat 'global' key in YAML should map to is_global."""
    data = {
        "task": {"name": "t", "description": "d"},
        "agents": {
            "heartbeat": [
                {"name": "reflect", "every": 1, "global": True},
            ]
        },
    }
    config = CoralConfig.from_dict(data)
    assert config.agents.heartbeat[0].is_global is True

    # Round-trip through to_dict
    d = config.to_dict()
    assert d["agents"]["heartbeat"][0]["global"] is True


def test_run_config_defaults():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
    )
    assert config.run.verbose is False
    assert config.run.ui is False
    assert config.run.session == "tmux"


def test_run_config_dotlist_override():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
    )
    merged = CoralConfig.merge_dotlist(config, ["run.session=local", "run.verbose=true"])
    assert merged.run.session == "local"
    assert merged.run.verbose is True
    assert merged.run.ui is False


def test_run_config_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
        run=RunConfig(verbose=True, ui=True, session="docker"),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.run.verbose is True
    assert restored.run.ui is True
    assert restored.run.session == "docker"


def test_to_dict_excludes_task_dir():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
    )
    config.task_dir = "/some/path"
    d = config.to_dict()
    assert "task_dir" not in d


# --- Warm-start config tests ---


def test_warmstart_config_defaults():
    data = {
        "task": {"name": "t", "description": "d"},
    }
    config = CoralConfig.from_dict(data)
    assert config.agents.warmstart.enabled is False


def test_warmstart_config_from_yaml():
    data = {
        "task": {"name": "t", "description": "d"},
        "agents": {
            "warmstart": {
                "enabled": True,
            },
        },
    }
    config = CoralConfig.from_dict(data)
    assert config.agents.warmstart.enabled is True


def test_warmstart_config_roundtrip():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
        agents=AgentConfig(
            warmstart=WarmStartConfig(enabled=True),
        ),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.agents.warmstart.enabled is True


def test_warmstart_dotlist_override():
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
    )
    merged = CoralConfig.merge_dotlist(config, [
        "agents.warmstart.enabled=true",
    ])
    assert merged.agents.warmstart.enabled is True
