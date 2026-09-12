"""Tests for the bundled scan-usage skill script (agent log usage attribution)."""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).parent.parent
    / "coral"
    / "template"
    / "skills"
    / "scan-usage"
    / "scripts"
    / "scan_usage.py"
)


@pytest.fixture(scope="module")
def scan_usage():
    spec = importlib.util.spec_from_file_location("scan_usage", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assistant_line(*blocks: dict) -> str:
    return json.dumps({"type": "assistant", "message": {"content": list(blocks)}})


def _tool_use(name: str, tool_input: dict) -> dict:
    return {"type": "tool_use", "name": name, "input": tool_input}


def _write_log(logs_dir: Path, name: str, lines: list[str]) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / name).write_text("\n".join(lines) + "\n")


def test_read_tool_counts_note_read(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            _assistant_line(
                _tool_use(
                    "Read", {"file_path": "/run/agents/agent-1/.claude/notes/experiments/greedy.md"}
                )
            )
        ],
    )
    notes, skills, unresolved = scan_usage.scan_logs(tmp_path)
    assert notes["experiments/greedy.md"]["reads"] == 1
    assert notes["experiments/greedy.md"]["readers"] == {"agent-1": 1}
    assert skills == {}
    assert unresolved == 0


def test_bash_cat_counts_read_but_redirect_counts_write(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-2.0.log",
        [
            _assistant_line(_tool_use("Bash", {"command": "cat .claude/notes/findings.md"})),
            _assistant_line(_tool_use("Bash", {"command": "echo hi > .claude/notes/mine.md"})),
            _assistant_line(
                _tool_use("Bash", {"command": "python x.py | tee /abs/path/.claude/notes/log.md"})
            ),
        ],
    )
    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["findings.md"]["reads"] == 1
    assert notes["mine.md"]["writes"] == 1
    assert notes["mine.md"]["reads"] == 0
    assert notes["log.md"]["writes"] == 1


def test_write_and_edit_tools_count_as_writes(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            _assistant_line(
                _tool_use("Write", {"file_path": ".claude/notes/new.md", "content": "x"})
            ),
            _assistant_line(_tool_use("Edit", {"file_path": ".claude/notes/new.md"})),
        ],
    )
    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["new.md"]["writes"] == 2
    assert notes["new.md"]["reads"] == 0


def test_glob_counts_browse_not_read(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [_assistant_line(_tool_use("Glob", {"pattern": ".claude/notes/research/topic.md"}))],
    )
    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["research/topic.md"]["browses"] == 1
    assert notes["research/topic.md"]["reads"] == 0


def test_tool_results_are_ignored(scan_usage, tmp_path):
    # A directory listing in a tool result must not mark notes as read.
    result_line = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "content": "found .claude/notes/a.md and .claude/notes/b.md",
                    }
                ]
            },
        }
    )
    _write_log(tmp_path, "agent-1.0.log", [result_line])
    notes, skills, _ = scan_usage.scan_logs(tmp_path)
    assert notes == {}
    assert skills == {}


def test_skill_uses_from_skill_tool_read_and_cli(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            _assistant_line(_tool_use("Skill", {"skill": "coral:deep-research", "args": "q"})),
            _assistant_line(
                _tool_use("Read", {"file_path": ".claude/skills/organize-files/SKILL.md"})
            ),
            _assistant_line(
                _tool_use(
                    "Bash", {"command": "python .claude/skills/organize-files/scripts/audit.sh"}
                )
            ),
            _assistant_line(_tool_use("Bash", {"command": "coral skills --read skill-creator"})),
        ],
    )
    _, skills, _ = scan_usage.scan_logs(tmp_path)
    assert skills["deep-research"]["uses"] == 1
    assert skills["organize-files"]["uses"] == 2
    assert skills["skill-creator"]["uses"] == 1


def test_authoring_a_skill_is_not_a_use(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            _assistant_line(_tool_use("Write", {"file_path": ".claude/skills/my-tool/SKILL.md"})),
            _assistant_line(
                _tool_use("Bash", {"command": "echo x > .claude/skills/my-tool/scripts/run.py"})
            ),
            _assistant_line(_tool_use("Glob", {"pattern": ".claude/skills/my-tool/*"})),
        ],
    )
    _, skills, _ = scan_usage.scan_logs(tmp_path)
    assert "my-tool" not in skills


def test_bare_directory_listing_matches_nothing(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            _assistant_line(
                _tool_use("Bash", {"command": "ls .claude/notes/ && ls .claude/skills/"})
            )
        ],
    )
    notes, skills, _ = scan_usage.scan_logs(tmp_path)
    assert notes == {}
    assert skills == {}


def test_coral_notes_read_counts_unresolved(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [_assistant_line(_tool_use("Bash", {"command": "coral notes --read 3"}))],
    )
    notes, _, unresolved = scan_usage.scan_logs(tmp_path)
    assert notes == {}
    assert unresolved == 1


def test_codex_style_command_events(scan_usage, tmp_path):
    lines = [
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "cat .codex/notes/plan.md"},
            }
        )
    ]
    _write_log(tmp_path, "agent-1.0.log", lines)
    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["plan.md"]["reads"] == 1


def test_agent_filter_and_multiple_logs(scan_usage, tmp_path):
    read = _assistant_line(_tool_use("Read", {"file_path": ".claude/notes/shared.md"}))
    _write_log(tmp_path, "agent-1.0.log", [read])
    _write_log(tmp_path, "agent-1.1.log", [read])
    _write_log(tmp_path, "agent-2.0.log", [read])

    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["shared.md"]["reads"] == 3
    assert notes["shared.md"]["readers"] == {"agent-1": 2, "agent-2": 1}

    notes, _, _ = scan_usage.scan_logs(tmp_path, only_agent="agent-2")
    assert notes["shared.md"]["readers"] == {"agent-2": 1}


def test_malformed_lines_are_skipped(scan_usage, tmp_path):
    _write_log(
        tmp_path,
        "agent-1.0.log",
        [
            "not json at all",
            '{"type": "assistant"}',
            '{"type": "assistant", "message": {"content": "plain string"}}',
            "[1, 2, 3]",
            _assistant_line(_tool_use("Read", {"file_path": ".claude/notes/ok.md"})),
        ],
    )
    notes, _, _ = scan_usage.scan_logs(tmp_path)
    assert notes["ok.md"]["reads"] == 1


def test_inventory_and_never_read(scan_usage, tmp_path):
    notes_dir = tmp_path / "notes"
    (notes_dir / "research").mkdir(parents=True)
    (notes_dir / "research" / "seen.md").write_text("x")
    (notes_dir / "research" / "unseen.md").write_text("x")
    (notes_dir / "_archive").mkdir()
    (notes_dir / "_archive" / "old.md").write_text("x")
    skills_dir = tmp_path / "skills"
    (skills_dir / "used-skill").mkdir(parents=True)
    (skills_dir / "used-skill" / "SKILL.md").write_text("x")
    (skills_dir / "dead-skill").mkdir()
    (skills_dir / "dead-skill" / "SKILL.md").write_text("x")

    note_files, skill_names = scan_usage.inventory(notes_dir, skills_dir)
    assert note_files == ["research/seen.md", "research/unseen.md"]
    assert skill_names == ["dead-skill", "used-skill"]


def test_cli_json_end_to_end(scan_usage, tmp_path):
    import subprocess
    import sys

    logs = tmp_path / "logs"
    _write_log(
        logs,
        "agent-1.0.log",
        [
            _assistant_line(_tool_use("Read", {"file_path": ".claude/notes/seen.md"})),
            _assistant_line(_tool_use("Skill", {"skill": "used-skill"})),
        ],
    )
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "seen.md").write_text("x")
    (notes_dir / "unseen.md").write_text("x")
    skills_dir = tmp_path / "skills"
    (skills_dir / "used-skill").mkdir(parents=True)
    (skills_dir / "used-skill" / "SKILL.md").write_text("x")
    (skills_dir / "dead-skill").mkdir()
    (skills_dir / "dead-skill" / "SKILL.md").write_text("x")

    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            str(logs),
            "--notes-dir",
            str(notes_dir),
            "--skills-dir",
            str(skills_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(proc.stdout)
    assert report["notes"]["never_read"] == ["unseen.md"]
    assert report["notes"]["usage"]["seen.md"]["reads"] == 1
    assert report["skills"]["never_used"] == ["dead-skill"]
    assert report["skills"]["usage"]["used-skill"]["uses"] == 1


def test_cli_missing_logs_dir_errors(tmp_path):
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(tmp_path / "nope")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "not found" in proc.stderr
