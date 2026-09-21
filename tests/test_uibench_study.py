"""Properties of the UI-Bench three-arm study materials in ``examples/uibench``.

These pin what makes the three arms a fair comparison: the arms are identical
wherever an agent can see, the committed configs are what the generator emits,
the yoke schedules are the hash-bound checkpoint kind the module accepts, and
the terminal-artifact judge never selects on the treatment's own score.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from coral.grader.evolution.policy import PolicyConfig

REPO = Path(__file__).resolve().parents[1]
UIBENCH = REPO / "examples" / "uibench"
CONFIGS = {
    "museum_static": ("static", "museum"),
    "museum_adaptive": ("adaptive", "museum"),
    "museum_yoked": ("yoked", "museum"),
    "fellowship_static": ("static", None),
    "fellowship_adaptive": ("adaptive", None),
    "fellowship_yoked": ("yoked", None),
}
SCHEDULES = {"museum": "museum_adaptive_r1.json", "fellowship": "fellowship_adaptive_r1.json"}


@pytest.fixture(scope="module")
def prompt_table():
    """The UI-Bench prompt table is fetched at a pinned revision and hash-verified,
    never committed (its dataset card declares no license). Regeneration tests
    skip offline; the tests that only read committed files do not depend on it."""
    sys.path.insert(0, str(UIBENCH))
    mt = importlib.import_module("make_task")
    try:
        return mt.prompt_table()
    except mt.PromptTableUnavailable as exc:
        pytest.skip(f"UI-Bench prompt table unavailable: {exc}")


def _gen(tmp_path: Path, arm: str, *, brief: str | None = None, schedule: Path | None = None):
    out = tmp_path / f"{arm}_{brief or 'uibench'}.yaml"
    cmd = [sys.executable, "make_task.py", "--id", "6", "--arm", arm, "-o", str(out)]
    cmd += ["--model", "claude-sonnet-4-5", "--attempts", "24"]
    if brief:
        cmd += [
            "--brief-file",
            f"briefs/{brief}.txt",
            "--task-name",
            "Rijksstudio voor Moderne Kunst",
        ]
    if schedule:
        cmd += ["--schedule", str(schedule)]
    subprocess.run(cmd, cwd=UIBENCH, check=True, capture_output=True)
    return out.read_text()


@pytest.mark.parametrize("brief", [None, "museum"])
def test_generated_arm_configs_are_identical_where_agents_can_see(tmp_path, brief, prompt_table):
    """The arm may differ only inside grader.args.evolution."""
    sched = tmp_path / "s.json"
    sched.write_text(
        json.dumps({"checkpoints": [8], "accepted_counts": [1], "schedule_sha256": "x"})
    )
    cfgs = {
        arm: yaml.safe_load(_gen(tmp_path, arm, brief=brief, schedule=sched))
        for arm in ("static", "adaptive", "yoked")
    }
    ref = cfgs["static"]
    for arm, cfg in cfgs.items():
        assert cfg["task"] == ref["task"], f"{arm} task block differs"
        assert cfg["agents"] == ref["agents"]
        assert cfg["run"] == ref["run"]
        assert cfg["workspace"] == ref["workspace"]
        grader = {k: v for k, v in cfg["grader"].items() if k != "args"}
        assert grader == {k: v for k, v in ref["grader"].items() if k != "args"}
        args = {k: v for k, v in cfg["grader"]["args"].items() if k != "evolution"}
        assert args == {k: v for k, v in ref["grader"]["args"].items() if k != "evolution"}
        assert cfg["grader"]["hide_args"] is True
        name = cfg["task"]["name"].casefold()
        for word in ("static", "adaptive", "yoked", "arm", "control", "blind"):
            assert word not in name, f"task name leaks the condition: {name}"


def test_generated_evolution_blocks_load_under_the_shipped_policy(tmp_path, prompt_table):
    """No legacy keys; adaptive has checkpoints; yoked names its schedule."""
    sched = tmp_path / "s.json"
    sched.write_text("{}")
    for arm in ("static", "adaptive", "yoked"):
        evo = yaml.safe_load(_gen(tmp_path, arm, schedule=sched))["grader"]["args"]["evolution"]
        cfg = PolicyConfig.from_args({k: v for k, v in evo.items() if k != "yoked_schedule_file"})
        assert cfg.mode == arm
        if arm == "adaptive":
            assert cfg.checkpoints == [8, 12, 16]
            assert cfg.max_new_criteria_per_round == 2
            assert cfg.window == 3
        if arm == "yoked":
            assert evo["yoked_schedule_file"] == str(sched)
        assert cfg.max_criteria == 11
        assert cfg.expansion_weight == 1.0


def test_generated_configs_leave_five_attempts_of_exposure(tmp_path, prompt_table):
    cfg = yaml.safe_load(_gen(tmp_path, "adaptive"))
    budget = cfg["run"]["stop"]["max_real_attempts"]
    assert cfg["grader"]["args"]["evolution"]["latest_publication_attempt"] == budget - 5


def test_seed_rubric_is_five_equally_weighted_criteria(tmp_path, prompt_table):
    crits = yaml.safe_load(_gen(tmp_path, "static"))["grader"]["args"]["criteria"]
    assert {c["name"] for c in crits} == {
        "Build Smoothness",
        "Implementation Quality",
        "Instruction Following",
        "Visual Quality",
        "Interaction Experience",
    }
    assert all(c["weight"] == 1.0 for c in crits)


def test_museum_brief_changes_the_brief_and_nothing_else(tmp_path, prompt_table):
    a = yaml.safe_load(_gen(tmp_path, "static"))
    b = yaml.safe_load(_gen(tmp_path, "static", brief="museum"))
    assert a["task"]["name"] != b["task"]["name"]
    assert a["task"]["description"] != b["task"]["description"]
    assert a["task"]["tips"] == b["task"]["tips"]
    a.pop("task")
    b.pop("task")
    assert a == b


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_committed_configs_are_what_the_generator_emits(tmp_path, name, prompt_table):
    """Configs are regenerated, never edited: a hand edit to one arm is a
    confound, and this is where it would be caught."""
    arm, brief = CONFIGS[name]
    schedule = None
    if arm == "yoked":
        schedule = Path("..") / "schedules" / SCHEDULES[brief or "fellowship"]
    expected = _gen(tmp_path, arm, brief=brief, schedule=schedule)
    committed = (UIBENCH / name / "task.yaml").read_text()
    assert committed == expected, f"{name}/task.yaml differs from make_task.py output"


@pytest.mark.parametrize("task", sorted(SCHEDULES))
def test_yoke_schedules_are_hash_bound_checkpoint_schedules(task):
    path = UIBENCH / "schedules" / SCHEDULES[task]
    sched = json.loads(path.read_text())
    assert sched["schedule_kind"] == "checkpoint"
    assert sched["checkpoints"] == [8, 12, 16]
    assert sched["accepted_counts"] == [2, 2, 2]
    assert sched["statuses"] == ["published"] * 3
    assert sched["complete"] is True
    # The same four fields the yoked grader hashes before it accepts a schedule.
    body = {k: sched.get(k) for k in ("checkpoints", "accepted_counts", "statuses", "complete")}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    assert sched["schedule_sha256"] == digest, "schedule body does not match its hash"


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_config_dirs_carry_the_seed_symlink(name):
    """workspace.repo_path resolves against the working directory; the seed
    symlink beside task.yaml is what CORAL copies into the run repo."""
    link = UIBENCH / name / "seed"
    assert link.is_symlink() and (link / "index.html").is_file()
    assert link.resolve() == (REPO / "examples" / "frontend-eval" / "seed").resolve()


def test_yoked_configs_point_at_their_adaptive_twin_schedule():
    for task, fname in SCHEDULES.items():
        cfg = yaml.safe_load((UIBENCH / f"{task}_yoked" / "task.yaml").read_text())
        assert cfg["grader"]["args"]["evolution"]["yoked_schedule_file"] == f"../schedules/{fname}"
        assert (
            UIBENCH / f"{task}_yoked" / cfg["grader"]["args"]["evolution"]["yoked_schedule_file"]
        ).exists()


def test_pilot_tasks_are_excluded_from_the_confirmatory_set():
    sys.path.insert(0, str(UIBENCH))
    mt = importlib.import_module("make_task")
    assert {2, 6, 18, 20}.isdisjoint(mt.CONFIRMATORY_IDS)


def test_a_tampered_prompt_table_is_refused(tmp_path):
    sys.path.insert(0, str(UIBENCH))
    mt = importlib.import_module("make_task")
    bad = tmp_path / "table.csv"
    bad.write_bytes(b"ID,Category\r\n1,x\r\n")
    with pytest.raises(mt.PromptTableUnavailable, match="sha256"):
        mt.prompt_table(bad)


def test_committed_configs_record_the_pinned_source():
    sys.path.insert(0, str(UIBENCH))
    mt = importlib.import_module("make_task")
    for name in CONFIGS:
        head = (UIBENCH / name / "task.yaml").read_text().split("\ntask:")[0]
        assert mt.DATASET_REVISION in head
        assert mt.DATASET_SHA256 in head
        assert "not redistributed" in head


def test_run_config_is_denied_to_agents(tmp_path):
    """hide_args puts the arm in .coral/private and the public config carries
    empty args; the worktree settings must deny both the private dir and the
    config file."""
    from coral.workspace.worktree import setup_claude_settings

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "config.yaml").write_text("task: {name: x}\n")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    setup_claude_settings(worktree, coral_dir, research=False)
    deny = " ".join(
        json.loads((worktree / ".claude" / "settings.local.json").read_text())["permissions"][
            "deny"
        ]
    )
    assert "config.yaml" in deny
    assert str(coral_dir.resolve() / "private") in deny


def test_judge_selects_on_recency_alone_never_on_grading_outcome(tmp_path):
    """Not on score (the treatment would choose its own exhibit) and not on
    evaluator success (failures cluster by agent)."""
    sys.path.insert(0, str(REPO / "examples" / "frontend-eval" / "grader" / "scripts"))
    mod = importlib.import_module("judge_final_artifacts")

    attempts = tmp_path / ".coral" / "public" / "attempts"
    attempts.mkdir(parents=True)
    rows = [
        ("a1c1", "agent-1", "improved", 0.99, "2026-09-04T01:00:00", False),
        ("a1c2", "agent-1", "regressed", 0.40, "2026-09-04T02:00:00", False),
        ("a2c1", "agent-2", "improved", 0.70, "2026-09-04T01:30:00", False),
        ("a3c1", "agent-3", "improved", 0.60, "2026-09-04T01:40:00", False),
        ("a3c2", "agent-3", "crashed", None, "2026-09-04T02:10:00", False),
        ("a4c1", "agent-4", "pending", None, "2026-09-04T02:20:00", False),
        ("a2c2", "agent-2", "improved", 0.95, "2026-09-04T03:00:00", True),
    ]
    for commit, agent, status, score, ts, archived in rows:
        (attempts / f"{commit}.json").write_text(
            json.dumps(
                {
                    "commit_hash": commit,
                    "agent_id": agent,
                    "status": status,
                    "score": score,
                    "timestamp": ts,
                    "metadata": {"archived": True} if archived else {},
                }
            )
        )
    picked = {a["agent"]: a["commit"] for a in mod.terminal_artifacts(tmp_path)}
    assert picked == {
        "agent-1": "a1c2",  # last, not best
        "agent-2": "a2c1",  # a2c2 is archived
        "agent-3": "a3c2",  # last is crashed and still counts
        "agent-4": "a4c1",  # last is pending and still counts
    }


def test_evidence_set_names_the_runs_of_record():
    manifest = json.loads((UIBENCH / "analysis" / "runs_manifest.json").read_text())
    assert {r["run_id"] for r in manifest["runs"]} == {
        f"{task}-{arm}-r1"
        for task in ("museum", "fellowship")
        for arm in ("static", "adaptive", "yoked")
    }
    assert all(r["protocol_version"] == 1 for r in manifest["runs"])
    chain = json.loads(
        (UIBENCH / "analysis" / "evidence" / "keyboard_operability_chain.json").read_text()
    )
    assert chain["chain"]["name"] == "Keyboard Operability of the Interaction Model"
    assert {a["agent"] for a in chain["chain"]["agents"]} == {
        "captain-ahab",
        "captain-nemo",
        "davy-jones",
        "jack-sparrow",
    }
    assert [
        a["in_origin_window"] for a in chain["chain"]["agents"] if a["agent"] == "davy-jones"
    ] == [False]
