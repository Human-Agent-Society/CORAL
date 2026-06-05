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
        grader=GraderConfig(
            entrypoint="my_pkg.grader:Grader",
            setup=["uv pip install -e ./my_pkg"],
            args={"k": 1},
        ),
        agents=AgentConfig(count=2, model="opus"),
    )

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.task.name == "test"
    assert restored.grader.entrypoint == "my_pkg.grader:Grader"
    assert restored.grader.setup == ["uv pip install -e ./my_pkg"]
    assert restored.grader.args == {"k": 1}
    assert restored.agents.count == 2
    assert restored.agents.model == "opus"


def test_config_from_dict():
    data = {
        "task": {"name": "t", "description": "d"},
        "grader": {"entrypoint": "kernel_builder.grader:Grader"},
    }
    config = CoralConfig.from_dict(data)
    assert config.task.name == "t"
    assert config.grader.entrypoint == "kernel_builder.grader:Grader"
    assert config.agents.count == 1  # default


def test_legacy_grader_type_rejected():
    """Removed grader.type field raises a ValueError with migration guidance."""
    data = {
        "task": {"name": "t", "description": "d"},
        "grader": {"type": "function"},
    }
    with pytest.raises(ValueError, match="grader.type"):
        CoralConfig.from_dict(data)


def test_legacy_grader_module_rejected():
    """Removed grader.module field raises a ValueError with migration guidance."""
    data = {
        "task": {"name": "t", "description": "d"},
        "grader": {"module": "my.module"},
    }
    with pytest.raises(ValueError, match="grader.module"):
        CoralConfig.from_dict(data)


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


def test_assignments_yaml_roundtrip():
    """agents.assignments survives a YAML to_yaml/from_yaml roundtrip."""
    from coral.config import AgentAssignmentConfig

    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
        agents=AgentConfig(
            assignments=[
                AgentAssignmentConfig(runtime="claude_code", model="opus", count=2),
                AgentAssignmentConfig(
                    runtime="codex",
                    model="gpt-5.4",
                    count=1,
                    runtime_options={"fast_mode": True},
                ),
            ],
        ),
    )
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert len(restored.agents.assignments) == 2
    assert restored.agents.assignments[0].runtime == "claude_code"
    assert restored.agents.assignments[0].model == "opus"
    assert restored.agents.assignments[0].count == 2
    assert restored.agents.assignments[1].runtime == "codex"
    assert restored.agents.assignments[1].runtime_options == {"fast_mode": True}


def test_assignments_model_default_from_runtime_via_preprocess():
    """Empty model on an assignment is back-filled from the runtime default."""
    data = {
        "task": {"name": "t", "description": "d"},
        "agents": {
            "assignments": [
                {"runtime": "codex", "count": 1},
            ],
        },
    }
    config = CoralConfig.from_dict(data)
    assert config.agents.assignments[0].model == "gpt-5.4"


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
    merged = CoralConfig.merge_dotlist(
        config,
        [
            "agents.warmstart.enabled=true",
        ],
    )
    assert merged.agents.warmstart.enabled is True


def test_skills_config_roundtrip():
    """agents.skills survives a YAML to_yaml/from_yaml roundtrip."""
    skills = ["./skills/test-skill", "./skills/other"]
    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
        agents=AgentConfig(skills=skills),
    )
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        config.to_yaml(f.name)
        restored = CoralConfig.from_yaml(f.name)

    assert restored.agents.skills == skills


def test_skills_config_defaults_empty():
    data = {"task": {"name": "t", "description": "d"}}
    config = CoralConfig.from_dict(data)
    assert config.agents.skills == []


def test_islands_defaults_single_island():
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
        }
    )
    assert cfg.islands.count == 1
    assert cfg.islands.migration.enabled is True
    assert cfg.islands.migration.every == 50
    assert cfg.islands.migration.rank_window == 20
    assert cfg.islands.migration.min_evals == 3
    assert cfg.islands.migration.dest_weighting == "score"
    assert cfg.islands.migration.max_per_cycle == 2
    assert cfg.islands.migration.notify_island is True


def test_islands_count_override():
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "islands": {"count": 4},
        }
    )
    assert cfg.islands.count == 4


def test_islands_migration_override():
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "islands": {"count": 2, "migration": {"every": 25, "dest_weighting": "uniform"}},
        }
    )
    assert cfg.islands.migration.every == 25
    assert cfg.islands.migration.dest_weighting == "uniform"


def test_islands_count_validation():
    import pytest

    with pytest.raises(ValueError, match="islands.count must be >= 1"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "islands": {"count": 0},
            }
        )


def test_migration_every_validation():
    import pytest

    with pytest.raises(ValueError, match="islands.migration.every must be >= 1"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "islands": {"migration": {"every": 0}},
            }
        )


def test_migration_rank_window_validation():
    import pytest

    with pytest.raises(ValueError, match="islands.migration.rank_window"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "islands": {"migration": {"every": 10, "rank_window": 20}},
            }
        )


def test_migration_dest_weighting_validation():
    import pytest

    with pytest.raises(ValueError, match="dest_weighting"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "islands": {"migration": {"dest_weighting": "nonsense"}},
            }
        )
