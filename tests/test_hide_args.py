"""grader.hide_args: grader arguments stay out of anything an agent can read,
through setup, grading and resume."""

from __future__ import annotations

import json

import yaml

from coral.config import CoralConfig
from coral.workspace.project import grader_config_path, save_run_config
from coral.workspace.worktree import setup_claude_settings

ARGS = {
    "criteria": [{"name": "Secret", "weight": 2.0, "description": "hidden"}],
    "evolution": {"mode": "adaptive", "checkpoints": [8]},
}


def _config(hide: bool) -> CoralConfig:
    return CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "grader": {"entrypoint": "x:Y", "hide_args": hide, "args": ARGS},
        }
    )


def test_hide_args_writes_a_full_private_copy_and_a_redacted_public_copy(tmp_path):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(True), coral_dir)
    private = yaml.safe_load((coral_dir / "private" / "config.yaml").read_text())
    public = yaml.safe_load((coral_dir / "config.yaml").read_text())
    assert private["grader"]["args"]["criteria"][0]["name"] == "Secret"
    assert public["grader"]["args"] == {}
    assert "Secret" not in (coral_dir / "config.yaml").read_text()
    assert grader_config_path(coral_dir) == coral_dir / "private" / "config.yaml"


def test_without_hide_args_there_is_one_config_and_graders_read_it(tmp_path):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(False), coral_dir)
    assert not (coral_dir / "private" / "config.yaml").exists()
    assert grader_config_path(coral_dir) == coral_dir / "config.yaml"
    assert yaml.safe_load((coral_dir / "config.yaml").read_text())["grader"]["args"]["criteria"]


def test_graders_load_their_arguments_from_the_private_copy(tmp_path):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(True), coral_dir)
    loaded = CoralConfig.from_yaml(grader_config_path(coral_dir))
    assert loaded.grader.args["criteria"][0]["weight"] == 2.0
    # the daemon resolves its config through the same function
    import inspect

    from coral.grader import daemon

    assert "grader_config_path" in inspect.getsource(daemon)


def test_resume_keeps_hidden_arguments_and_applies_overrides_to_both_copies(tmp_path):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(True), coral_dir)
    # what cmd_resume does: read the authoritative copy, merge overrides, write back
    config = CoralConfig.from_yaml(grader_config_path(coral_dir))
    config = CoralConfig.merge_dotlist(config, ["run.stop.max_real_attempts=30"])
    save_run_config(config, coral_dir)
    private = yaml.safe_load((coral_dir / "private" / "config.yaml").read_text())
    public = yaml.safe_load((coral_dir / "config.yaml").read_text())
    assert private["grader"]["args"]["criteria"][0]["name"] == "Secret", (
        "resume must not drop grader args"
    )
    assert private["run"]["stop"]["max_real_attempts"] == 30
    assert public["run"]["stop"]["max_real_attempts"] == 30, "eval hooks read the public copy"
    assert public["grader"]["args"] == {}, "an override must not re-expose hidden args"
    # resuming from the public copy would silently lose the arguments; that is the bug this guards
    assert CoralConfig.from_yaml(coral_dir / "config.yaml").grader.args == {}


def test_cmd_resume_reads_the_authoritative_config():
    import inspect

    from coral.cli import start

    src = inspect.getsource(start.cmd_resume)
    assert "grader_config_path(coral_dir)" in src and "save_run_config(config, coral_dir)" in src
    assert 'coral_dir / "config.yaml"' not in src


def test_the_run_config_and_the_private_dir_are_denied_to_agents(tmp_path):
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    save_run_config(_config(True), coral_dir)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    setup_claude_settings(worktree, coral_dir, research=False)
    deny = " ".join(
        json.loads((worktree / ".claude" / "settings.local.json").read_text())["permissions"][
            "deny"
        ]
    )
    assert str(coral_dir.resolve() / "config.yaml") in deny
    assert str(coral_dir.resolve() / "private") in deny


def test_turning_hide_args_off_removes_the_private_copy_so_it_cannot_shadow_the_public_one(
    tmp_path,
):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(True), coral_dir)
    assert grader_config_path(coral_dir) == coral_dir / "private" / "config.yaml"
    save_run_config(_config(False), coral_dir)
    assert not (coral_dir / "private" / "config.yaml").exists()
    assert grader_config_path(coral_dir) == coral_dir / "config.yaml"
    assert (
        CoralConfig.from_yaml(grader_config_path(coral_dir)).grader.args["criteria"][0]["name"]
        == "Secret"
    )


def test_turning_hide_args_on_moves_the_arguments_out_of_the_public_copy(tmp_path):
    coral_dir = tmp_path / ".coral"
    save_run_config(_config(False), coral_dir)
    assert "Secret" in (coral_dir / "config.yaml").read_text()
    save_run_config(_config(True), coral_dir)
    assert "Secret" not in (coral_dir / "config.yaml").read_text()
    assert (
        CoralConfig.from_yaml(grader_config_path(coral_dir)).grader.args["criteria"][0]["name"]
        == "Secret"
    )
