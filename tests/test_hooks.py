"""Tests for eval implementation and Claude Code settings."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from coral.grader.daemon import process_pending_once
from coral.hooks.post_commit import (
    _increment_eval_count,
    submit_eval,
)
from coral.workspace import setup_claude_settings
from coral.workspace.worktree import _deep_merge_settings

# These tests deliberately use the deprecated eval/grader.py loading path —
# silence the warning suite-wide.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _submit_and_grade(message: str, agent_id: str, workdir: str):
    """Submit a pending attempt, then synchronously drain the grader queue.

    Mirrors the production flow (submit + async grader + wait) without
    needing to spawn a separate grader daemon process in tests.
    """
    from coral.hooks.post_commit import _find_coral_dir
    from coral.hub.attempts import read_attempt, read_eval_count

    # Stage+commit+write pending; no wait because there's no daemon running.
    pending = submit_eval(message=message, agent_id=agent_id, workdir=workdir, wait=False)

    coral_dir = _find_coral_dir(Path(workdir).resolve())
    assert coral_dir is not None
    process_pending_once(coral_dir)

    final = read_attempt(coral_dir, pending.commit_hash)
    assert final is not None
    try:
        final._eval_count = read_eval_count(coral_dir)  # type: ignore[attr-defined]
    except Exception:
        pass
    return final


def _setup_repo_with_config(base_dir: Path) -> Path:
    """Create a git repo with .coral/config.yaml wired to eval/grader.py."""
    repo = base_dir / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"], capture_output=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], capture_output=True)

    # Create a file and .gitignore, then make an initial commit
    (repo / "hello.py").write_text("print('hello')\n")
    (repo / ".gitignore").write_text(".coral/\n.coral_dir\n.claude/\n.coral_agent_id\nCLAUDE.md\n")
    subprocess.run(["git", "-C", str(repo), "add", "hello.py", ".gitignore"], capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Initial"], capture_output=True, check=True
    )

    # Set up .coral directory with config + eval/grader.py
    coral_dir = repo / ".coral"
    coral_dir.mkdir()
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    eval_dir = coral_dir / "private" / "eval"
    eval_dir.mkdir(parents=True)

    # Write .coral_dir breadcrumb (as write_coral_dir does)
    (repo / ".coral_dir").write_text(str(coral_dir.resolve()))

    (eval_dir / "grader.py").write_text(
        "from coral.grader.task_grader import TaskGrader\n"
        "class Grader(TaskGrader):\n"
        "    def evaluate(self):\n"
        "        return 0.75\n"
    )

    config = {
        "task": {"name": "test_task", "description": "A test"},
        "grader": {},
        "agents": {"count": 1},
        "sharing": {"attempts": True, "notes": True, "skills": True},
        "workspace": {"base_dir": str(repo), "repo_path": str(repo)},
    }
    with open(coral_dir / "config.yaml", "w") as f:
        yaml.dump(config, f)

    return repo


def test_submit_eval_pending_then_graded():
    """submit_eval writes a pending record; daemon finalizes it with a score."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        (repo / "hello.py").write_text("print('hello world')\n")

        sys.path.insert(0, str(repo))
        try:
            # Stage without running grader yet.
            pending = submit_eval(
                message="Update hello message",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert pending.status == "pending"
            assert pending.score is None

            attempt_file = repo / ".coral" / "public" / "attempts" / f"{pending.commit_hash}.json"
            assert attempt_file.exists()
            pending_data = json.loads(attempt_file.read_text())
            assert pending_data["status"] == "pending"
            assert pending_data["score"] is None

            # Drain the grader queue synchronously.
            process_pending_once(repo / ".coral")

            final_data = json.loads(attempt_file.read_text())
            assert final_data["score"] == 0.75
            assert final_data["status"] == "improved"
            assert final_data["commit_hash"] == pending.commit_hash
        finally:
            sys.path.pop(0)


def test_submit_eval_no_changes():
    """submit_eval should fail if there are no changes to commit."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            submit_eval(
                message="No changes",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Nothing to commit" in str(e)
        finally:
            sys.path.pop(0)


def test_eval_count_and_reflection():
    """Test that eval count increments."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "public").mkdir()

        # Counter starts at 0, increments to 1
        assert _increment_eval_count(coral_dir) == 1
        assert _increment_eval_count(coral_dir) == 2
        assert _increment_eval_count(coral_dir) == 3

        # Check file contents
        assert (coral_dir / "public" / "eval_count").read_text() == "3"


def test_submit_eval_tracks_eval_count():
    """Integration: daemon bumps the eval counter when finalizing attempts."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            (repo / "hello.py").write_text("print('v1')\n")
            a1 = _submit_and_grade("v1", "agent-test", str(repo))
            assert getattr(a1, "_eval_count", None) == 1

            (repo / "hello.py").write_text("print('v2')\n")
            a2 = _submit_and_grade("v2", "agent-test", str(repo))
            assert getattr(a2, "_eval_count", None) == 2
        finally:
            sys.path.pop(0)


def _set_grader_config(repo: Path, **fields) -> None:
    """Rewrite .coral/config.yaml's grader section with the given overrides."""
    cfg_path = repo / ".coral" / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("grader", {}).update(fields)
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)


def _head_hash(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_submit_eval_rejects_when_agent_at_pending_limit():
    """Default cap is 1: a second submit while the first is pending must raise
    and must not create a new commit."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))
        sys.path.insert(0, str(repo))
        try:
            (repo / "hello.py").write_text("print('v1')\n")
            first = submit_eval(
                message="v1",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert first.status == "pending"
            head_after_first = _head_hash(repo)

            # Second submit while first is still pending — must reject.
            (repo / "hello.py").write_text("print('v2')\n")
            with pytest.raises(RuntimeError, match=r"pending attempt"):
                submit_eval(
                    message="v2",
                    agent_id="agent-test",
                    workdir=str(repo),
                    wait=False,
                )

            # No orphan commit was created by the rejected submit.
            assert _head_hash(repo) == head_after_first
        finally:
            sys.path.pop(0)


def test_submit_eval_allows_after_drain():
    """After the daemon grades the pending attempt, a new submit succeeds."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))
        sys.path.insert(0, str(repo))
        try:
            (repo / "hello.py").write_text("print('v1')\n")
            _submit_and_grade("v1", "agent-test", str(repo))

            (repo / "hello.py").write_text("print('v2')\n")
            second = submit_eval(
                message="v2",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert second.status == "pending"
        finally:
            sys.path.pop(0)


def test_submit_eval_respects_higher_limit():
    """grader.max_pending_per_agent: 3 lets three pending stack, rejects the fourth."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))
        _set_grader_config(repo, max_pending_per_agent=3)

        sys.path.insert(0, str(repo))
        try:
            for i in range(3):
                (repo / "hello.py").write_text(f"print('v{i}')\n")
                submit_eval(
                    message=f"v{i}",
                    agent_id="agent-test",
                    workdir=str(repo),
                    wait=False,
                )

            (repo / "hello.py").write_text("print('overflow')\n")
            with pytest.raises(RuntimeError, match=r"pending attempt"):
                submit_eval(
                    message="overflow",
                    agent_id="agent-test",
                    workdir=str(repo),
                    wait=False,
                )
        finally:
            sys.path.pop(0)


def test_submit_eval_unlimited_when_zero():
    """grader.max_pending_per_agent: 0 disables the cap entirely."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))
        _set_grader_config(repo, max_pending_per_agent=0)

        sys.path.insert(0, str(repo))
        try:
            for i in range(5):
                (repo / "hello.py").write_text(f"print('v{i}')\n")
                submit_eval(
                    message=f"v{i}",
                    agent_id="agent-test",
                    workdir=str(repo),
                    wait=False,
                )
            # All five sit in the queue as pending; nothing was rejected.
            attempts_dir = repo / ".coral" / "public" / "attempts"
            assert len(list(attempts_dir.glob("*.json"))) == 5
        finally:
            sys.path.pop(0)


def test_submit_eval_per_agent_isolation():
    """A pending submission from agent-A must not block agent-B from submitting."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))
        sys.path.insert(0, str(repo))
        try:
            (repo / "hello.py").write_text("print('a')\n")
            submit_eval(message="a", agent_id="agent-A", workdir=str(repo), wait=False)

            # agent-A is at its limit, but agent-B has no pending attempts.
            (repo / "hello.py").write_text("print('b')\n")
            second = submit_eval(
                message="b",
                agent_id="agent-B",
                workdir=str(repo),
                wait=False,
            )
            assert second.status == "pending"
            assert second.agent_id == "agent-B"
        finally:
            sys.path.pop(0)


def test_submit_eval_sets_shared_state_hash():
    """submit_eval should checkpoint shared state and store hash in the attempt.

    The checkpoint runs before write_attempt, so the first eval has no prior
    shared state changes (hash is None). The second eval sees the first eval's
    attempt JSON and eval_count, producing a non-None hash.
    """
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            # First eval — no prior shared state changes, hash should be None
            (repo / "hello.py").write_text("print('v1')\n")
            a1 = _submit_and_grade("first", "agent-test", str(repo))
            assert a1.shared_state_hash is None

            # Second eval — first eval wrote attempt JSON + eval_count, so checkpoint finds changes
            (repo / "hello.py").write_text("print('v2')\n")
            a2 = _submit_and_grade("second", "agent-test", str(repo))
            assert a2.shared_state_hash is not None
            assert len(a2.shared_state_hash) == 40
            # Parent shared state hash comes from the first attempt
            assert a2.parent_shared_state_hash == a1.shared_state_hash

            # Verify hashes were persisted in the attempt JSON
            attempt_file = repo / ".coral" / "public" / "attempts" / f"{a2.commit_hash}.json"
            data = json.loads(attempt_file.read_text())
            assert data["shared_state_hash"] == a2.shared_state_hash
        finally:
            sys.path.pop(0)


# --- setup_claude_settings tests ---


def test_setup_claude_settings_permissions():
    """Settings should grant tool permissions."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir)

        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        private_dir = str(coral_dir.resolve() / "private")

        worktree_str = str(worktree.resolve())
        agents_dir = str(coral_dir.resolve().parent / "agents")

        # No sandbox
        assert "sandbox" not in settings

        # Permission allow rules grant agent autonomy
        allow = settings["permissions"]["allow"]
        # Bash is unscoped; Read/Edit/Write scoped to own worktree
        assert "Bash" in allow
        assert any("Read" in r and worktree_str in r for r in allow)
        assert any("Read" in r and agents_dir in r for r in allow)
        assert any("Edit" in r and worktree_str in r for r in allow)
        assert any("Write" in r and worktree_str in r for r in allow)
        assert "WebSearch" in allow  # research=True by default
        assert "WebFetch" in allow

        # Permission deny rules block git and private dir
        deny = settings["permissions"]["deny"]
        assert "Bash(git *)" in deny
        assert any(private_dir in r for r in deny)
        assert not any("WebSearch" in r for r in deny)

        assert "hooks" not in settings

        # Auto mode is always enabled
        assert settings["permissions"]["defaultMode"] == "auto"


def test_setup_claude_settings_no_research():
    """Settings should deny WebSearch/WebFetch when research=False."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir, research=False)

        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]

        assert "WebSearch" not in allow
        assert "WebFetch" not in allow
        assert "WebSearch" in deny
        assert "WebFetch" in deny


# --- _deep_merge_settings unit tests ---


def test_deep_merge_dicts_recurse():
    base = {"permissions": {"defaultMode": "auto", "allow": ["Bash"]}}
    overlay = {"permissions": {"defaultMode": "plan"}}
    merged = _deep_merge_settings(base, overlay)
    # Scalar in nested dict: overlay wins, sibling list preserved
    assert merged["permissions"]["defaultMode"] == "plan"
    assert merged["permissions"]["allow"] == ["Bash"]


def test_deep_merge_lists_concatenate():
    base = {"permissions": {"allow": ["Bash"], "deny": ["Bash(git *)"]}}
    overlay = {"permissions": {"allow": ["mcp__db__query"], "deny": ["Bash(rm *)"]}}
    merged = _deep_merge_settings(base, overlay)
    # User's permission rules append to CORAL's defaults — they don't replace
    assert merged["permissions"]["allow"] == ["Bash", "mcp__db__query"]
    assert merged["permissions"]["deny"] == ["Bash(git *)", "Bash(rm *)"]


def test_deep_merge_adds_new_keys():
    base = {"permissions": {"allow": ["Bash"]}}
    overlay = {
        "mcpServers": {"db": {"command": "uvx", "args": ["mcp-db"]}},
        "env": {"FOO": "bar"},
    }
    merged = _deep_merge_settings(base, overlay)
    assert merged["mcpServers"] == {"db": {"command": "uvx", "args": ["mcp-db"]}}
    assert merged["env"] == {"FOO": "bar"}
    # Original keys untouched
    assert merged["permissions"]["allow"] == ["Bash"]


def test_deep_merge_does_not_mutate_base():
    base = {"permissions": {"allow": ["Bash"]}}
    overlay = {"permissions": {"allow": ["WebSearch"]}}
    _deep_merge_settings(base, overlay)
    assert base == {"permissions": {"allow": ["Bash"]}}


def test_deep_merge_scalar_overrides_list():
    """Type mismatch: overlay wins (defensive — shouldn't happen in practice)."""
    base = {"foo": [1, 2]}
    overlay = {"foo": "scalar"}
    merged = _deep_merge_settings(base, overlay)
    assert merged["foo"] == "scalar"


# --- setup_claude_settings with overrides ---


def test_setup_claude_settings_with_overrides_merges_mcp_and_env():
    """Override dict merges into the generated settings.local.json."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        overrides = {
            "mcpServers": {"db": {"command": "uvx", "args": ["mcp-db"]}},
            "env": {"MY_CUSTOM_VAR": "value"},
            "permissions": {"allow": ["mcp__db__query"]},
        }

        setup_claude_settings(worktree, coral_dir, settings_overrides=overrides)
        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())

        # Override-only fields land verbatim
        assert settings["mcpServers"] == {"db": {"command": "uvx", "args": ["mcp-db"]}}
        assert settings["env"] == {"MY_CUSTOM_VAR": "value"}

        # User's allow rule appended to CORAL's defaults — defaults are still there
        allow = settings["permissions"]["allow"]
        assert "Bash" in allow  # CORAL default preserved
        assert "mcp__db__query" in allow  # user addition appended

        # CORAL deny rules still in place (not touched by override)
        deny = settings["permissions"]["deny"]
        assert "Bash(git *)" in deny


def test_setup_claude_settings_overrides_can_replace_default_mode():
    """Scalar in nested dict gets overlaid (overlay wins)."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(
            worktree,
            coral_dir,
            settings_overrides={"permissions": {"defaultMode": "plan"}},
        )
        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        assert settings["permissions"]["defaultMode"] == "plan"
        # Other CORAL-managed permission fields untouched
        assert "Bash" in settings["permissions"]["allow"]


def test_setup_claude_settings_overrides_coexist_with_gateway():
    """Gateway env block and override env block both end up merged."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(
            worktree,
            coral_dir,
            gateway_url="http://localhost:4000",
            gateway_api_key="sk-test",
            settings_overrides={"env": {"USER_VAR": "user-value"}},
        )
        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        # Gateway-injected env vars remain
        assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://localhost:4000"
        assert settings["env"]["ANTHROPIC_API_KEY"] == "sk-test"
        # User-supplied env var added
        assert settings["env"]["USER_VAR"] == "user-value"


def test_setup_claude_settings_no_overrides_unchanged():
    """settings_overrides=None matches pre-feature behavior exactly."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir)
        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        # No surprise fields
        assert set(settings.keys()) == {"permissions"}


# --- AgentManager._load_settings_overrides ---


def _make_manager_for_overrides(tmpdir: Path, task_dir: Path | None):
    """Build a minimal AgentManager that can call _load_settings_overrides."""
    from coral.agent.manager import AgentManager
    from coral.config import AgentConfig, CoralConfig, TaskConfig

    config = CoralConfig(
        task=TaskConfig(name="t", description="d"),
        agents=AgentConfig(),
    )
    config.task_dir = task_dir
    return AgentManager(config, config_dir=task_dir)


def test_load_settings_overrides_absolute_path():
    with tempfile.TemporaryDirectory() as d:
        d_path = Path(d)
        settings_file = d_path / "claude.json"
        settings_file.write_text(json.dumps({"env": {"FOO": "bar"}}))
        manager = _make_manager_for_overrides(d_path, task_dir=d_path)
        loaded = manager._load_settings_overrides({"settings_path": str(settings_file)})
        assert loaded == {"env": {"FOO": "bar"}}


def test_load_settings_overrides_relative_to_task_dir():
    with tempfile.TemporaryDirectory() as d:
        d_path = Path(d)
        (d_path / "agent1-settings.json").write_text(json.dumps({"env": {"A": "1"}}))
        manager = _make_manager_for_overrides(d_path, task_dir=d_path)
        loaded = manager._load_settings_overrides({"settings_path": "agent1-settings.json"})
        assert loaded == {"env": {"A": "1"}}


def test_load_settings_overrides_returns_none_without_key():
    manager = _make_manager_for_overrides(Path("/tmp"), task_dir=Path("/tmp"))
    assert manager._load_settings_overrides({}) is None
    assert manager._load_settings_overrides({"add_dirs": ["/x"]}) is None
    assert manager._load_settings_overrides(None) is None  # type: ignore[arg-type]


def test_load_settings_overrides_missing_file_raises():
    with tempfile.TemporaryDirectory() as d:
        manager = _make_manager_for_overrides(Path(d), task_dir=Path(d))
        with pytest.raises(FileNotFoundError, match="settings_path"):
            manager._load_settings_overrides({"settings_path": "does-not-exist.json"})


def test_load_settings_overrides_invalid_json_raises():
    with tempfile.TemporaryDirectory() as d:
        d_path = Path(d)
        bad = d_path / "bad.json"
        bad.write_text("{not json")
        manager = _make_manager_for_overrides(d_path, task_dir=d_path)
        with pytest.raises(ValueError, match="not valid JSON"):
            manager._load_settings_overrides({"settings_path": str(bad)})


def test_load_settings_overrides_non_dict_raises():
    with tempfile.TemporaryDirectory() as d:
        d_path = Path(d)
        list_file = d_path / "list.json"
        list_file.write_text(json.dumps(["a", "b"]))
        manager = _make_manager_for_overrides(d_path, task_dir=d_path)
        with pytest.raises(ValueError, match="JSON object at the top level"):
            manager._load_settings_overrides({"settings_path": str(list_file)})
