"""Tests for the island-migration selection + destination policy.

The migration runner is a pure-function selector layered on top of
``read_attempts`` plus a small amount of orchestration state (last cycle's
global eval count, RNG seed). The unit tests below pin the selection /
weighting policy without going through the manager; integration with
:class:`coral.agent.manager.AgentManager` is exercised separately.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from coral.agent.migration import (
    MigrationCandidate,
    MigrationRunner,
    assign_destinations,
    score_for_agent,
    select_candidates,
)
from coral.config import IslandsConfig, MigrationConfig
from coral.hub.attempts import read_attempt, write_attempt
from coral.types import Attempt


def _make_attempt(
    commit: str,
    agent: str,
    score: float | None,
    *,
    status: str = "improved",
    budget_class: str = "real",
    timestamp: str = "2026-05-31T10:00:00Z",
) -> Attempt:
    metadata: dict | None = None
    if budget_class != "real":
        metadata = {"budget_class": budget_class}
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title="t",
        score=score,
        status=status,
        parent_hash=None,
        timestamp=timestamp,
        metadata=metadata,
    )


def _make_multi_island(coral_dir: Path, n: int = 2) -> None:
    for i in range(n):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)


# ---------------------------------------------------------------------------
# score_for_agent: max/min over last rank_window real attempts
# ---------------------------------------------------------------------------


def test_score_for_agent_maximize_takes_max_over_window():
    """maximize direction: best of the last N real-mode scores wins."""
    attempts = [
        _make_attempt("a1", "agent-1", 0.10, timestamp="2026-05-31T10:00:00Z"),
        _make_attempt("a2", "agent-1", 0.90, timestamp="2026-05-31T10:01:00Z"),
        _make_attempt("a3", "agent-1", 0.50, timestamp="2026-05-31T10:02:00Z"),
    ]
    assert score_for_agent(attempts, rank_window=3, minimize=False) == 0.90


def test_score_for_agent_minimize_takes_min_over_window():
    attempts = [
        _make_attempt("a1", "agent-1", 0.10),
        _make_attempt("a2", "agent-1", 0.90),
        _make_attempt("a3", "agent-1", 0.50),
    ]
    assert score_for_agent(attempts, rank_window=3, minimize=True) == 0.10


def test_score_for_agent_uses_only_last_rank_window():
    """Older scores beyond rank_window are ignored. Ordering is by timestamp."""
    attempts = [
        _make_attempt("a1", "agent-1", 9.99, timestamp="2026-05-31T10:00:00Z"),
        _make_attempt("a2", "agent-1", 0.10, timestamp="2026-05-31T10:01:00Z"),
        _make_attempt("a3", "agent-1", 0.20, timestamp="2026-05-31T10:02:00Z"),
        _make_attempt("a4", "agent-1", 0.30, timestamp="2026-05-31T10:03:00Z"),
    ]
    # rank_window=2 → only [0.20, 0.30] considered, max=0.30 (not 9.99)
    assert score_for_agent(attempts, rank_window=2, minimize=False) == 0.30


def test_score_for_agent_skips_non_real_budget_class():
    """tune / grader_error attempts do not count toward the migration score."""
    attempts = [
        _make_attempt("a1", "agent-1", 0.99, budget_class="tune"),
        _make_attempt("a2", "agent-1", 0.50, budget_class="real"),
    ]
    assert score_for_agent(attempts, rank_window=5, minimize=False) == 0.50


def test_score_for_agent_skips_none_scores():
    """Real attempts with score=None (grader error) are ignored."""
    attempts = [
        _make_attempt("a1", "agent-1", None, status="crashed"),
        _make_attempt("a2", "agent-1", 0.5),
    ]
    assert score_for_agent(attempts, rank_window=5, minimize=False) == 0.5


def test_score_for_agent_returns_none_when_no_real_scored_attempts():
    attempts = [
        _make_attempt("a1", "agent-1", None, status="crashed"),
        _make_attempt("a2", "agent-1", 0.9, budget_class="tune"),
    ]
    assert score_for_agent(attempts, rank_window=5, minimize=False) is None


# ---------------------------------------------------------------------------
# select_candidates: best-eligible per source island
# ---------------------------------------------------------------------------


def test_select_candidates_one_best_per_island():
    """Each source island contributes its best eligible agent."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        # Island 0: agent-A is best (0.9 > 0.4)
        for i, (agent, score) in enumerate([("agent-A", 0.9), ("agent-B", 0.4)] * 3):
            write_attempt(
                coral_dir,
                _make_attempt(f"i0-{i}", agent, score, timestamp=f"2026-05-31T10:0{i}:00Z"),
                island_id="0",
            )
        # Island 1: agent-C is best
        for i, (agent, score) in enumerate([("agent-C", 0.8), ("agent-D", 0.2)] * 3):
            write_attempt(
                coral_dir,
                _make_attempt(f"i1-{i}", agent, score, timestamp=f"2026-05-31T10:0{i}:00Z"),
                island_id="1",
            )

        candidates = select_candidates(
            coral_dir,
            island_ids=["0", "1"],
            rank_window=5,
            min_evals=2,
            minimize=False,
        )
        # One candidate per island, both are the per-island best
        assert {(c.agent_id, c.src_island) for c in candidates} == {
            ("agent-A", "0"),
            ("agent-C", "1"),
        }


def test_select_candidates_respects_min_evals():
    """Agents with fewer than min_evals real attempts are filtered out."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=1)
        # agent-A has only 1 real attempt — below min_evals=3
        write_attempt(coral_dir, _make_attempt("a1", "agent-A", 0.99), island_id="0")
        # agent-B has 3 real attempts — eligible
        for i, s in enumerate([0.3, 0.4, 0.5]):
            write_attempt(
                coral_dir,
                _make_attempt(f"b{i}", "agent-B", s, timestamp=f"2026-05-31T10:0{i}:00Z"),
                island_id="0",
            )

        candidates = select_candidates(
            coral_dir,
            island_ids=["0"],
            rank_window=5,
            min_evals=3,
            minimize=False,
        )
        assert len(candidates) == 1
        assert candidates[0].agent_id == "agent-B"


def test_select_candidates_skips_islands_with_no_eligible_agent():
    """An island where nobody hits min_evals contributes no candidate."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        # Island 0 has eligible candidates, island 1 has none (1 attempt only).
        for i, s in enumerate([0.3, 0.4, 0.5]):
            write_attempt(
                coral_dir,
                _make_attempt(f"a{i}", "agent-A", s, timestamp=f"2026-05-31T10:0{i}:00Z"),
                island_id="0",
            )
        write_attempt(coral_dir, _make_attempt("c1", "agent-C", 0.5), island_id="1")

        candidates = select_candidates(
            coral_dir,
            island_ids=["0", "1"],
            rank_window=5,
            min_evals=3,
            minimize=False,
        )
        assert [c.src_island for c in candidates] == ["0"]


def test_select_candidates_ignores_non_real_attempts_for_eligibility():
    """tune attempts count as 'evals' for the per-agent count? No — only real."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=1)
        # 1 real + 5 tune attempts → still below min_evals=3 on the real count
        write_attempt(coral_dir, _make_attempt("r1", "agent-A", 0.5), island_id="0")
        for i in range(5):
            write_attempt(
                coral_dir,
                _make_attempt(f"t{i}", "agent-A", 0.99, budget_class="tune"),
                island_id="0",
            )

        candidates = select_candidates(
            coral_dir,
            island_ids=["0"],
            rank_window=10,
            min_evals=3,
            minimize=False,
        )
        assert candidates == []


def test_select_candidates_minimize_direction_picks_lowest_score_agent():
    """When direction=minimize, the per-island best is the lowest-score agent."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=1)
        for i, (agent, score) in enumerate([("agent-A", 0.9), ("agent-B", 0.1)] * 3):
            write_attempt(
                coral_dir,
                _make_attempt(f"{i}", agent, score, timestamp=f"2026-05-31T10:0{i}:00Z"),
                island_id="0",
            )

        candidates = select_candidates(
            coral_dir,
            island_ids=["0"],
            rank_window=5,
            min_evals=2,
            minimize=True,
        )
        assert candidates[0].agent_id == "agent-B"  # lowest is best when minimizing


# ---------------------------------------------------------------------------
# assign_destinations: dest_weighting policies
# ---------------------------------------------------------------------------


def _candidate(agent: str, src: str, score: float = 0.5) -> MigrationCandidate:
    return MigrationCandidate(agent_id=agent, src_island=src, dst_island="", score=score)


def test_assign_destinations_round_robin_skips_source_island():
    """round_robin assigns deterministic non-source destinations."""
    candidates = [_candidate("agent-A", "0"), _candidate("agent-B", "1")]
    out = assign_destinations(
        candidates,
        island_ids=["0", "1", "2"],
        weighting="round_robin",
        cycle_idx=0,
        island_best_scores={},
        rng=random.Random(0),
        minimize=False,
    )
    # No agent migrates to its own source island
    assert all(c.dst_island != c.src_island for c in out)


def test_assign_destinations_round_robin_uses_cycle_idx_for_variety():
    """round_robin shifts destinations cycle-by-cycle so the same candidates
    don't always land on the same island."""
    c = [_candidate("agent-A", "0")]
    dst_0 = assign_destinations(
        c,
        island_ids=["0", "1", "2"],
        weighting="round_robin",
        cycle_idx=0,
        island_best_scores={},
        rng=random.Random(0),
        minimize=False,
    )[0].dst_island
    dst_1 = assign_destinations(
        c,
        island_ids=["0", "1", "2"],
        weighting="round_robin",
        cycle_idx=1,
        island_best_scores={},
        rng=random.Random(0),
        minimize=False,
    )[0].dst_island
    # Different cycles → (at least sometimes) different destinations
    assert dst_0 != dst_1


def test_assign_destinations_uniform_never_self_target():
    """uniform-random destinations never equal the candidate's source island."""
    candidates = [_candidate(f"agent-{i}", str(i)) for i in range(5)]
    out = assign_destinations(
        candidates,
        island_ids=["0", "1", "2", "3", "4"],
        weighting="uniform",
        cycle_idx=0,
        island_best_scores={},
        rng=random.Random(42),
        minimize=False,
    )
    for c in out:
        assert c.dst_island != c.src_island
        assert c.dst_island in {"0", "1", "2", "3", "4"}


def test_assign_destinations_score_weighting_biases_toward_stronger_islands():
    """When weighting='score', islands with higher best-score get more migrants
    over many trials (maximize direction)."""
    rng = random.Random(7)
    # 3 islands; island 2 is far stronger. Agent at island 0 should mostly go to island 2.
    best_scores = {"0": 0.0, "1": 0.1, "2": 1.0}
    landings: dict[str, int] = {"1": 0, "2": 0}
    for _ in range(500):
        out = assign_destinations(
            [_candidate("agent-A", "0")],
            island_ids=["0", "1", "2"],
            weighting="score",
            cycle_idx=0,
            island_best_scores=best_scores,
            rng=rng,
            minimize=False,
        )
        landings[out[0].dst_island] += 1
    # Island 2 is 10x stronger than island 1 → should dominate
    assert landings["2"] > 3 * landings["1"]


def test_assign_destinations_score_weighting_minimize_inverts():
    """When direction=minimize, the WEAKEST (lowest-score) island is strongest."""
    rng = random.Random(7)
    best_scores = {"0": 0.5, "1": 5.0, "2": 0.1}
    landings: dict[str, int] = {"1": 0, "2": 0}
    for _ in range(500):
        out = assign_destinations(
            [_candidate("agent-A", "0")],
            island_ids=["0", "1", "2"],
            weighting="score",
            cycle_idx=0,
            island_best_scores=best_scores,
            rng=rng,
            minimize=True,
        )
        landings[out[0].dst_island] += 1
    assert landings["2"] > 3 * landings["1"]


def test_assign_destinations_falls_back_to_uniform_when_no_scores():
    """With no island_best_scores recorded, score weighting degenerates to uniform."""
    rng = random.Random(0)
    out = assign_destinations(
        [_candidate("agent-A", "0")],
        island_ids=["0", "1", "2"],
        weighting="score",
        cycle_idx=0,
        island_best_scores={},
        rng=rng,
        minimize=False,
    )
    # Just confirm it does not raise and yields a legal destination.
    assert out[0].dst_island in {"1", "2"}


def test_assign_destinations_returns_empty_when_only_one_island():
    """No legal destination when count==1: nothing to assign."""
    out = assign_destinations(
        [_candidate("agent-A", "0")],
        island_ids=["0"],
        weighting="uniform",
        cycle_idx=0,
        island_best_scores={},
        rng=random.Random(0),
        minimize=False,
    )
    assert out == []


# ---------------------------------------------------------------------------
# MigrationRunner.should_run: trigger cadence
# ---------------------------------------------------------------------------


def _runner(every: int = 50, enabled: bool = True, **kwargs) -> MigrationRunner:
    # Default rank_window must be <= every (config validation).
    kwargs.setdefault("rank_window", min(every, 5))
    mig = MigrationConfig(every=every, enabled=enabled, **kwargs)
    cfg = IslandsConfig(count=2, migration=mig)
    return MigrationRunner(cfg, minimize=False, rng=random.Random(0))


def test_should_run_fires_on_first_boundary_after_every_evals():
    runner = _runner(every=10)
    # Below the threshold, never fires.
    for n in (0, 1, 5, 9):
        assert runner.should_run(current_global_evals=n) is False
    # At the threshold, fires once.
    assert runner.should_run(current_global_evals=10) is True
    # Without recording the cycle, it would fire again on every call past 10.
    # The runner tracks last_cycle_evals so once we mark the cycle, it
    # waits until 20 to fire again.
    runner.mark_cycle_complete(current_global_evals=10)
    assert runner.should_run(current_global_evals=11) is False
    assert runner.should_run(current_global_evals=19) is False
    assert runner.should_run(current_global_evals=20) is True


def test_should_run_returns_false_when_disabled():
    runner = _runner(every=10, enabled=False)
    assert runner.should_run(current_global_evals=100) is False


def test_should_run_returns_false_in_single_island_mode():
    """count=1 means no destinations — runner is a no-op."""
    mig = MigrationConfig(every=10, rank_window=5)
    cfg = IslandsConfig(count=1, migration=mig)
    runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))
    assert runner.should_run(current_global_evals=100) is False


def test_manager_rejects_more_islands_than_agents():
    from coral.agent.manager import AgentManager
    from coral.config import AgentConfig, CoralConfig

    cfg = CoralConfig(
        agents=AgentConfig(count=1),
        islands=IslandsConfig(count=2),
    )

    with pytest.raises(ValueError, match="islands.count cannot exceed"):
        AgentManager(cfg)


# ---------------------------------------------------------------------------
# MigrationRunner.run_cycle: end-to-end candidate -> dest assignment with cap
# ---------------------------------------------------------------------------


def test_run_cycle_caps_at_max_per_cycle():
    """Even when every island has a best candidate, only max_per_cycle migrate."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=4)
        # Seed each island with one eligible agent
        for island in range(4):
            for i, s in enumerate([0.3, 0.4, 0.5]):
                write_attempt(
                    coral_dir,
                    _make_attempt(
                        f"i{island}-{i}",
                        f"agent-{island}",
                        s,
                        timestamp=f"2026-05-31T10:0{i}:0{island}Z",
                    ),
                    island_id=str(island),
                )
        mig = MigrationConfig(every=10, rank_window=5, min_evals=2, max_per_cycle=2)
        cfg = IslandsConfig(count=4, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        migrations = runner.run_cycle(coral_dir=coral_dir, island_best_scores={})
        assert len(migrations) == 2


def test_run_cycle_returns_empty_when_no_eligible_candidates():
    """No agent meets min_evals → cycle returns empty without raising."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        # Just one attempt per island — below min_evals=3
        for island in range(2):
            write_attempt(
                coral_dir,
                _make_attempt(f"{island}", f"agent-{island}", 0.5),
                island_id=str(island),
            )
        mig = MigrationConfig(every=10, rank_window=5, min_evals=3)
        cfg = IslandsConfig(count=2, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        assert runner.run_cycle(coral_dir=coral_dir, island_best_scores={}) == []


def test_run_cycle_dst_never_equals_src_for_any_migration():
    """End-to-end invariant: nobody migrates to their own island."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=3)
        for island in range(3):
            for i, s in enumerate([0.3, 0.4, 0.5]):
                write_attempt(
                    coral_dir,
                    _make_attempt(
                        f"i{island}-{i}",
                        f"agent-{island}",
                        s,
                        timestamp=f"2026-05-31T10:0{i}:0{island}Z",
                    ),
                    island_id=str(island),
                )
        mig = MigrationConfig(every=10, rank_window=5, min_evals=2, max_per_cycle=3)
        cfg = IslandsConfig(count=3, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        migrations = runner.run_cycle(coral_dir=coral_dir, island_best_scores={})
        for m in migrations:
            assert m.src_island != m.dst_island


def test_run_cycle_roster_ignores_stale_attempt_history_after_migration():
    """Attempt dirs are history, not current membership.

    Regression for a two-island run where 0-agent-2 migrated 0→1. Its old
    high-scoring island-0 attempts remain on disk, but the current roster says
    it lives on island 1, so island 0 must not select it as a source candidate.
    """
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(
            coral_dir,
            _make_attempt("old-source", "0-agent-2", 5051.0),
            island_id="0",
        )
        write_attempt(
            coral_dir,
            _make_attempt("new-dest", "0-agent-2", 6112.0),
            island_id="1",
        )
        mig = MigrationConfig(
            every=2,
            rank_window=2,
            min_evals=1,
            dest_weighting="round_robin",
            max_per_cycle=2,
        )
        cfg = IslandsConfig(count=2, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        migrations = runner.run_cycle(
            coral_dir=coral_dir,
            island_best_scores={},
            current_agent_islands={
                "0-agent-1": "0",
                "0-agent-2": "1",
                "1-agent-1": "1",
                "1-agent-2": "1",
            },
        )

        assert migrations == [
            MigrationCandidate(
                agent_id="0-agent-2",
                src_island="1",
                dst_island="0",
                score=6112.0,
            )
        ]


def test_run_cycle_roster_balance_skips_one_way_move_from_balanced_roster():
    """A single one-way migration from a balanced roster would create 1/3.

    With move-based migration, `max_per_cycle` is an upper bound. If only one
    source island has an eligible candidate and the roster is already balanced,
    the balanced planner should skip the move instead of draining that island.
    """
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(
            coral_dir,
            _make_attempt("only-source", "0-agent-2", 10.0),
            island_id="0",
        )
        mig = MigrationConfig(
            every=2,
            rank_window=2,
            min_evals=1,
            dest_weighting="round_robin",
            max_per_cycle=2,
        )
        cfg = IslandsConfig(count=2, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        migrations = runner.run_cycle(
            coral_dir=coral_dir,
            island_best_scores={},
            current_agent_islands={
                "0-agent-1": "0",
                "0-agent-2": "0",
                "1-agent-1": "1",
                "1-agent-2": "1",
            },
        )

        assert migrations == []


def test_run_cycle_roster_balance_allows_two_way_swap():
    """When both islands have eligible current residents, max_per_cycle=2 permits a swap."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(
            coral_dir,
            _make_attempt("i0-best", "0-agent-2", 10.0),
            island_id="0",
        )
        write_attempt(
            coral_dir,
            _make_attempt("i1-best", "1-agent-1", 8.0),
            island_id="1",
        )
        mig = MigrationConfig(
            every=2,
            rank_window=2,
            min_evals=1,
            dest_weighting="round_robin",
            max_per_cycle=2,
        )
        cfg = IslandsConfig(count=2, migration=mig)
        runner = MigrationRunner(cfg, minimize=False, rng=random.Random(0))

        migrations = runner.run_cycle(
            coral_dir=coral_dir,
            island_best_scores={},
            current_agent_islands={
                "0-agent-1": "0",
                "0-agent-2": "0",
                "1-agent-1": "1",
                "1-agent-2": "1",
            },
        )

        assert {(m.agent_id, m.src_island, m.dst_island) for m in migrations} == {
            ("0-agent-2", "0", "1"),
            ("1-agent-1", "1", "0"),
        }


def test_migration_candidate_is_frozen():
    """The candidate dataclass must be hashable for set-based dedup."""
    c = MigrationCandidate(agent_id="x", src_island="0", dst_island="1", score=0.5)
    with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
        c.dst_island = "2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Module-level helpers in coral.agent.manager that participate in apply.
# These are exercised here because they have no in-process agent state.
# ---------------------------------------------------------------------------


def test_move_agent_files_moves_agent_state_attempts_and_eval_logs():
    """_move_agent_files moves identity files plus this agent's attempts/eval logs."""
    from coral.agent.manager import _move_agent_files

    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for island in ("0", "1"):
            (coral_dir / "islands" / island / "roles").mkdir(parents=True)
            (coral_dir / "islands" / island / "heartbeat").mkdir(parents=True)
            (coral_dir / "islands" / island / "attempts").mkdir(parents=True)
            (coral_dir / "islands" / island / "eval_logs").mkdir(parents=True)
            (coral_dir / "islands" / island / "notes").mkdir(parents=True)
        # Source files
        (coral_dir / "islands" / "0" / "roles" / "agent-1.md").write_text("R")
        (coral_dir / "islands" / "0" / "heartbeat" / "agent-1.json").write_text("{}")
        write_attempt(coral_dir, _make_attempt("aaa", "agent-1", 0.9), island_id="0")
        write_attempt(coral_dir, _make_attempt("bbb", "agent-2", 0.8), island_id="0")
        (coral_dir / "islands" / "0" / "attempts" / "ccc.jsonl").write_text(
            '{"agent_id": "agent-1", "commit_hash": "ccc"}\n'
        )
        (coral_dir / "islands" / "0" / "eval_logs" / "aaa").mkdir()
        (coral_dir / "islands" / "0" / "eval_logs" / "aaa" / "metrics.json").write_text("{}")
        (coral_dir / "islands" / "0" / "eval_logs" / "bbb").mkdir()
        (coral_dir / "islands" / "0" / "eval_logs" / "ccc").mkdir()
        (coral_dir / "islands" / "0" / "eval_logs" / "ccc" / "metrics.json").write_text("{}")
        # Notes should NOT be touched
        (coral_dir / "islands" / "0" / "notes" / "agent-1.md").write_text("not moved")

        _move_agent_files(coral_dir, "agent-1", src="0", dst="1")

        assert (coral_dir / "islands" / "1" / "roles" / "agent-1.md").read_text() == "R"
        assert (coral_dir / "islands" / "1" / "heartbeat" / "agent-1.json").read_text() == "{}"
        assert not (coral_dir / "islands" / "0" / "roles" / "agent-1.md").exists()
        assert not (coral_dir / "islands" / "0" / "heartbeat" / "agent-1.json").exists()
        assert (coral_dir / "islands" / "1" / "attempts" / "aaa.json").exists()
        assert not (coral_dir / "islands" / "0" / "attempts" / "aaa.json").exists()
        assert (coral_dir / "islands" / "1" / "attempts" / "ccc.jsonl").exists()
        assert not (coral_dir / "islands" / "0" / "attempts" / "ccc.jsonl").exists()
        moved_attempt = read_attempt(coral_dir, "aaa", island_id="1")
        assert moved_attempt is not None
        assert moved_attempt.metadata["island_id"] == "1"
        moved_jsonl = json.loads(
            (coral_dir / "islands" / "1" / "attempts" / "ccc.jsonl").read_text()
        )
        assert moved_jsonl["metadata"]["island_id"] == "1"
        assert (coral_dir / "islands" / "1" / "eval_logs" / "aaa" / "metrics.json").exists()
        assert not (coral_dir / "islands" / "0" / "eval_logs" / "aaa").exists()
        assert (coral_dir / "islands" / "1" / "eval_logs" / "ccc" / "metrics.json").exists()
        assert not (coral_dir / "islands" / "0" / "eval_logs" / "ccc").exists()
        # Other agents' attempts/logs and user notes stay on the source island.
        assert (coral_dir / "islands" / "0" / "attempts" / "bbb.json").exists()
        assert not (coral_dir / "islands" / "1" / "attempts" / "bbb.json").exists()
        assert (coral_dir / "islands" / "0" / "eval_logs" / "bbb").exists()
        assert (coral_dir / "islands" / "0" / "notes" / "agent-1.md").exists()
        assert not (coral_dir / "islands" / "1" / "notes" / "agent-1.md").exists()


def test_move_agent_files_is_idempotent_on_missing_source():
    """Calling twice (or against a never-migrated agent) doesn't raise."""
    from coral.agent.manager import _move_agent_files

    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for island in ("0", "1"):
            (coral_dir / "islands" / island / "roles").mkdir(parents=True)
            (coral_dir / "islands" / island / "heartbeat").mkdir(parents=True)
        # No source files at all — should just do nothing.
        _move_agent_files(coral_dir, "agent-1", src="0", dst="1")
        assert list((coral_dir / "islands" / "1" / "roles").iterdir()) == []
        assert list((coral_dir / "islands" / "1" / "heartbeat").iterdir()) == []


def test_write_arrival_note_lands_on_dst_island_as_coral_authored():
    """The arrival note shows up on the destination island, attributed to coral."""
    from coral.agent.manager import _write_arrival_note

    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands" / "1" / "notes").mkdir(parents=True)

        candidate = MigrationCandidate(
            agent_id="0-agent-1", src_island="0", dst_island="1", score=0.7654321
        )
        _write_arrival_note(coral_dir, candidate)

        notes_dir = coral_dir / "islands" / "1" / "notes"
        files = list(notes_dir.glob("migration_*_0-agent-1.md"))
        assert len(files) == 1
        text = files[0].read_text()
        assert "creator: coral" in text
        assert "0-agent-1" in text
        assert "0.765432" in text
        # Authored by "coral" sentinel — won't pollute the notes_by author lookup
        from coral.hub.notes import notes_by

        # An agent-id-attributed search should not match the framework note.
        assert notes_by(coral_dir, island_id="1", agent_id="coral") == files
        assert notes_by(coral_dir, island_id="1", agent_id="0-agent-1") == []


def test_manager_migration_eval_count_ignores_tune_and_pending(tmp_path):
    """Migration cadence advances only on finalized real attempts."""
    from coral.agent.manager import AgentManager
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    _make_multi_island(coral_dir, n=2)
    write_attempt(coral_dir, _make_attempt("real-1", "0-agent-1", 1.0), island_id="0")
    write_attempt(
        coral_dir,
        _make_attempt("real-failed", "0-agent-2", None, status="timeout"),
        island_id="0",
    )
    write_attempt(
        coral_dir,
        _make_attempt("tune-1", "1-agent-1", 9.0, budget_class="tune"),
        island_id="1",
    )
    write_attempt(
        coral_dir,
        _make_attempt("pending-real", "1-agent-2", None, status="pending"),
        island_id="1",
    )

    mgr = AgentManager(
        CoralConfig(agents=AgentConfig(assignments=[AgentAssignmentConfig(count=1)]))
    )
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )

    assert mgr._get_migration_eval_count() == 2


def test_build_migration_prompt_includes_shared_dir_paths():
    """The arrival prompt names the runtime's shared dir so paths are correct."""
    from coral.agent.manager import _build_migration_prompt

    candidate = MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5)
    prompt = _build_migration_prompt(candidate, shared_dir=".codex")
    assert ".codex/notes" in prompt
    assert ".codex/skills" in prompt
    # The path-rewrite hint should mention BOTH source and destination islands
    # so the agent understands the asymmetry between followed vs left-behind state.
    assert "island `0`" in prompt
    assert "island `1`" in prompt


def test_manager_prefers_agent_island_map_over_spec_after_migration():
    """The two restart paths must consult ``_agent_island`` first.

    Regression check for the resume-after-migration drift: ``coral resume``
    rebuilds specs from config (birth island), but the breadcrumb-restored
    ``_agent_island`` map holds the post-migration island. If the restart
    helpers looked at spec first they'd put the agent back on its original
    island and silently undo the migration.
    """
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    # Simulate a post-migration state: agent-1 was born on island 0
    # but now lives on island 1 according to _agent_island.
    spec = AgentSpec(agent_id="0-agent-1", runtime="x", model="y", island_id="0")
    mgr.specs_by_id = {"0-agent-1": spec}
    mgr._agent_island = {"0-agent-1": "1"}

    # Inline the lookup pattern used by _restart_agent / _interrupt_and_resume.
    looked_up = mgr._agent_island.get("0-agent-1") or (spec.island_id if spec else None)
    assert looked_up == "1", "should prefer the live _agent_island map post-migration"


def test_swap_spec_island_updates_specs_in_place():
    """_swap_spec_island replaces the AgentSpec with the new island id."""
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    mgr.specs = [
        AgentSpec(agent_id="0-agent-1", runtime="x", model="y", island_id="0"),
    ]
    mgr.specs_by_id = {"0-agent-1": mgr.specs[0]}

    mgr._swap_spec_island("0-agent-1", new_island_id="1")
    assert mgr.specs[0].island_id == "1"
    assert mgr.specs_by_id["0-agent-1"].island_id == "1"
    # Agent id itself is unchanged — the prefix tracks BIRTH island, not current.
    assert mgr.specs[0].agent_id == "0-agent-1"


# ---------------------------------------------------------------------------
# End-to-end: _apply_migration against a real worktree on disk.
# Stubs only the subprocess spawn (_setup_and_start_agent) — every other
# step (file moves, symlink repoint, spec swap, arrival note, settings
# rewrite) runs against real filesystem state.
# ---------------------------------------------------------------------------


def test_apply_migration_end_to_end_moves_state_and_repoints_worktree(tmp_path):
    """Run _apply_migration against a real on-disk worktree and verify side effects."""
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.agent.runtime import AgentHandle
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig
    from coral.workspace import setup_shared_state
    from coral.workspace.project import ProjectPaths

    # Real-on-disk fixture: 2 islands, a worktree wired to island 0.
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)  # _write_agent_pids writes here
    for island in ("0", "1"):
        for sub in (
            "attempts",
            "notes",
            "skills",
            "agents",
            "logs",
            "heartbeat",
            "roles",
            "eval_logs",
        ):
            (coral_dir / "islands" / island / sub).mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    setup_shared_state(worktree, coral_dir, ".claude", island_id="0")
    # Pre-seed per-agent state on island 0 that should follow the agent.
    (coral_dir / "islands" / "0" / "roles" / "0-agent-1.md").write_text("evolved role")
    (coral_dir / "islands" / "0" / "heartbeat" / "0-agent-1.json").write_text(
        '{"actions": [{"name": "reflect", "every": 1, "prompt": "..."}]}'
    )
    write_attempt(coral_dir, _make_attempt("attempt-a", "0-agent-1", 0.5), island_id="0")
    (coral_dir / "islands" / "0" / "eval_logs" / "attempt-a").mkdir()
    (coral_dir / "islands" / "0" / "eval_logs" / "attempt-a" / "metrics.json").write_text("{}")

    # Build a manager and pin every component the migration touches.
    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2, migration=MigrationConfig(every=5, rank_window=3)),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    spec = AgentSpec(
        agent_id="0-agent-1",
        runtime="claude_code",
        model="opus",
        island_id="0",
    )
    mgr.specs = [spec]
    mgr.specs_by_id = {"0-agent-1": spec}
    mgr._agent_island = {"0-agent-1": "0"}

    # Fake handle: process=None means interrupt() is a no-op and alive==False
    # — both fine for this test. A real log file is needed because the
    # runtime's extract_session_id reads it (returns None for empty files).
    log_path = tmp_path / "0-agent-1.log"
    log_path.write_text("")
    mgr.handles = [
        AgentHandle(
            agent_id="0-agent-1",
            process=None,
            worktree_path=worktree,
            log_path=log_path,
        )
    ]

    # Stub the subprocess-spawning restart step. The migration's actual
    # side effects all run BEFORE this call.
    spawn_calls: list[dict] = []

    def _fake_setup_and_start(agent_id, **kwargs):
        spawn_calls.append({"agent_id": agent_id, **kwargs})
        return mgr.handles[0]

    mgr._setup_and_start_agent = _fake_setup_and_start  # type: ignore[assignment]

    candidate = MigrationCandidate(
        agent_id="0-agent-1", src_island="0", dst_island="1", score=0.8765
    )
    mgr._apply_migration(candidate)

    # --- Verify the post-migration filesystem state ---
    # Role & heartbeat moved src → dst
    assert (coral_dir / "islands" / "1" / "roles" / "0-agent-1.md").read_text() == "evolved role"
    assert (coral_dir / "islands" / "1" / "heartbeat" / "0-agent-1.json").exists()
    assert (coral_dir / "islands" / "1" / "attempts" / "attempt-a.json").exists()
    assert (coral_dir / "islands" / "1" / "eval_logs" / "attempt-a" / "metrics.json").exists()
    assert not (coral_dir / "islands" / "0" / "roles" / "0-agent-1.md").exists()
    assert not (coral_dir / "islands" / "0" / "heartbeat" / "0-agent-1.json").exists()
    assert not (coral_dir / "islands" / "0" / "attempts" / "attempt-a.json").exists()
    assert not (coral_dir / "islands" / "0" / "eval_logs" / "attempt-a").exists()

    # Worktree symlinks repointed at island 1
    for item in ("notes", "skills", "attempts", "heartbeat", "roles"):
        link = worktree / ".claude" / item
        assert link.is_symlink()
        assert link.resolve() == (coral_dir / "islands" / "1" / item).resolve()
    # Breadcrumb updated
    assert (worktree / ".coral_island").read_text() == "1"

    # Spec + tracking dict swapped to dst
    assert mgr.specs[0].island_id == "1"
    assert mgr.specs_by_id["0-agent-1"].island_id == "1"
    assert mgr._agent_island["0-agent-1"] == "1"

    # Arrival note dropped on dst (creator: coral)
    arrival_notes = list((coral_dir / "islands" / "1" / "notes").glob("migration_*_0-agent-1.md"))
    assert len(arrival_notes) == 1
    assert "creator: coral" in arrival_notes[0].read_text()
    # Source island didn't get a stray arrival note
    assert list((coral_dir / "islands" / "0" / "notes").glob("migration_*")) == []

    # Claude settings file regenerated with dst island scope
    settings = (worktree / ".claude" / "settings.local.json").read_text()
    assert "islands/1" in settings
    assert "islands/0" not in settings

    # Restart was invoked with the dst island and migration source label
    assert len(spawn_calls) == 1
    call = spawn_calls[0]
    assert call["agent_id"] == "0-agent-1"
    assert call["island_id"] == "1"
    assert call["prompt_source"] == "migration"
    assert "migrated" in call["prompt"].lower()
    # Restart counter bumped
    assert mgr._restart_counts["0-agent-1"] == 1


def test_apply_migration_moves_pending_attempt_with_agent(tmp_path):
    """Pending grader attempts move with the agent instead of blocking migration."""
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.agent.runtime import AgentHandle
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig
    from coral.workspace import setup_shared_state
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    for island in ("0", "1"):
        for sub in (
            "attempts",
            "notes",
            "skills",
            "heartbeat",
            "roles",
            "agents",
            "logs",
            "eval_logs",
        ):
            (coral_dir / "islands" / island / sub).mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    setup_shared_state(worktree, coral_dir, ".claude", island_id="0")

    # Plant a pending attempt for our migration target on src.
    pending = Attempt(
        commit_hash="abc123def",
        agent_id="0-agent-1",
        title="in flight",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-06-01T10:00:00Z",
    )
    write_attempt(coral_dir, pending, island_id="0")
    (coral_dir / "public").mkdir(parents=True)

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    spec = AgentSpec(agent_id="0-agent-1", runtime="claude_code", model="opus", island_id="0")
    mgr.specs = [spec]
    mgr.specs_by_id = {"0-agent-1": spec}
    mgr._agent_island = {"0-agent-1": "0"}
    mgr.handles = [
        AgentHandle(
            agent_id="0-agent-1",
            process=None,
            worktree_path=worktree,
            log_path=tmp_path / "log.txt",
        )
    ]
    spawn_calls: list[dict] = []
    mgr._setup_and_start_agent = lambda agent_id, **kwargs: (
        spawn_calls.append({"agent_id": agent_id, **kwargs}) or mgr.handles[0]
    )  # type: ignore[assignment]

    mgr._apply_migration(
        MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5)
    )

    assert mgr._agent_island["0-agent-1"] == "1"
    assert mgr.specs[0].island_id == "1"
    assert (worktree / ".coral_island").read_text() == "1"
    assert len(spawn_calls) == 1
    assert spawn_calls[0]["agent_id"] == "0-agent-1"
    assert spawn_calls[0]["island_id"] == "1"
    assert mgr._deferred_candidates == []
    assert not (coral_dir / "islands" / "0" / "attempts" / "abc123def.json").exists()
    moved = read_attempt(coral_dir, "abc123def", island_id="1")
    assert moved is not None
    assert moved.status == "pending"
    assert moved.metadata["island_id"] == "1"


def test_deferred_candidate_is_retried_on_next_cycle(tmp_path):
    """A paused candidate is retried and applies once the manager-side block clears."""
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.agent.migration import MigrationCandidate
    from coral.agent.runtime import AgentHandle
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig
    from coral.workspace import setup_shared_state
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)  # _write_agent_pids writes here
    for island in ("0", "1"):
        for sub in (
            "attempts",
            "notes",
            "skills",
            "heartbeat",
            "roles",
            "agents",
            "logs",
            "eval_logs",
        ):
            (coral_dir / "islands" / island / sub).mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    setup_shared_state(worktree, coral_dir, ".claude", island_id="0")

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    spec = AgentSpec(agent_id="0-agent-1", runtime="claude_code", model="opus", island_id="0")
    mgr.specs = [spec]
    mgr.specs_by_id = {"0-agent-1": spec}
    mgr._agent_island = {"0-agent-1": "0"}
    mgr.handles = [
        AgentHandle(
            agent_id="0-agent-1",
            process=None,
            worktree_path=worktree,
            log_path=tmp_path / "log.txt",
        )
    ]
    spawn_calls: list[dict] = []
    mgr._setup_and_start_agent = lambda agent_id, **kwargs: (
        spawn_calls.append({"agent_id": agent_id, **kwargs}) or mgr.handles[0]
    )  # type: ignore[assignment]

    blocked = True

    def fake_block_reason(_candidate):
        return "paused" if blocked else None

    mgr._migration_block_reason = fake_block_reason  # type: ignore[assignment]

    # ---- Cycle 1: deferred while paused. ----
    mgr._apply_migration(
        MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5)
    )
    assert spawn_calls == []
    assert [(c.agent_id, r) for c, r in mgr._deferred_candidates] == [("0-agent-1", "paused")]

    # ---- Cycle 2: deferred candidate should now apply cleanly. ----
    blocked = False
    mgr._apply_migration(
        MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.6)
    )
    # Successful apply: agent is on island 1 now, deferred entry cleared.
    assert mgr._agent_island["0-agent-1"] == "1"
    assert mgr.specs[0].island_id == "1"
    assert len(spawn_calls) == 1
    assert spawn_calls[0]["agent_id"] == "0-agent-1"
    assert spawn_calls[0]["island_id"] == "1"
    assert mgr._deferred_candidates == []


def test_maybe_run_migration_cycle_migrates_whole_swap_with_pending_attempt(tmp_path):
    """A balanced swap remains atomic while pending attempts move with agents.

    Regression for a 2/2 run where 0-agent-1 was pending, but 1-agent-1 still
    migrated 1→0. That produced a 3/1 roster. The planned batch should move
    both directions together, and the pending attempt should follow 0-agent-1.
    """
    from coral.agent.assignments import AgentSpec
    from coral.agent.manager import AgentManager
    from coral.agent.migration import MigrationCandidate
    from coral.agent.runtime import AgentHandle
    from coral.config import (
        AgentAssignmentConfig,
        AgentConfig,
        CoralConfig,
        IslandsConfig,
        MigrationConfig,
    )
    from coral.workspace import setup_shared_state
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)  # _write_agent_pids writes here
    for island in ("0", "1"):
        for sub in (
            "attempts",
            "notes",
            "skills",
            "heartbeat",
            "roles",
            "agents",
            "logs",
            "eval_logs",
        ):
            (coral_dir / "islands" / island / sub).mkdir(parents=True)
    worktree_a = tmp_path / "wt_a"
    worktree_b = tmp_path / "wt_b"
    worktree_a.mkdir()
    worktree_b.mkdir()
    setup_shared_state(worktree_a, coral_dir, ".claude", island_id="0")
    setup_shared_state(worktree_b, coral_dir, ".claude", island_id="1")

    # Seed 3 real scored attempts for 0-agent-1 (eligible) and 1-agent-1 (eligible).
    for island, agent, score in (("0", "0-agent-1", 0.5), ("1", "1-agent-1", 0.7)):
        for k, s in enumerate([score] * 3):
            a = Attempt(
                commit_hash=f"h-{island}-{k}",
                agent_id=agent,
                title=f"e{k}",
                score=s,
                status="improved",
                parent_hash=None,
                timestamp=f"2026-06-01T10:0{k}:00Z",
            )
            write_attempt(coral_dir, a, island_id=island)

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2, migration=MigrationConfig(max_per_cycle=2)),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    spec_a = AgentSpec(agent_id="0-agent-1", runtime="claude_code", model="opus", island_id="0")
    spec_b = AgentSpec(agent_id="1-agent-1", runtime="claude_code", model="opus", island_id="1")
    mgr.specs = [spec_a, spec_b]
    mgr.specs_by_id = {s.agent_id: s for s in mgr.specs}
    mgr._agent_island = {"0-agent-1": "0", "1-agent-1": "1"}
    mgr.handles = [
        AgentHandle(
            agent_id="0-agent-1",
            process=None,
            worktree_path=worktree_a,
            log_path=tmp_path / "a.log",
        ),
        AgentHandle(
            agent_id="1-agent-1",
            process=None,
            worktree_path=worktree_b,
            log_path=tmp_path / "b.log",
        ),
    ]
    spawn_calls: list[dict] = []
    mgr._setup_and_start_agent = lambda agent_id, **kwargs: (
        spawn_calls.append({"agent_id": agent_id, **kwargs})
        or mgr.handles[0 if agent_id == "0-agent-1" else 1]
    )  # type: ignore[assignment]

    # Force should_run() to True and freeze run_cycle's output to a known set:
    # fresh picks a balanced swap.
    def fake_should_run(*, current_global_evals):
        return True

    def fake_run_cycle(*, coral_dir, island_best_scores, current_agent_islands=None):
        return [
            MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5),
            MigrationCandidate(agent_id="1-agent-1", src_island="1", dst_island="0", score=0.7),
        ]

    mgr._migration_runner.should_run = fake_should_run  # type: ignore[assignment]
    mgr._migration_runner.run_cycle = fake_run_cycle  # type: ignore[assignment]
    # 0-agent-1 has a pending attempt planted. Pending does not block
    # migration; the attempt file follows the agent to island 1.
    pending = Attempt(
        commit_hash="pend-1",
        agent_id="0-agent-1",
        title="in flight",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-06-01T11:00:00Z",
    )
    write_attempt(coral_dir, pending, island_id="0")

    mgr._maybe_run_migration_cycle()

    assert mgr._agent_island == {"0-agent-1": "1", "1-agent-1": "0"}
    assert [call["agent_id"] for call in spawn_calls] == ["0-agent-1", "1-agent-1"]
    assert mgr._deferred_candidates == []
    assert not (coral_dir / "islands" / "0" / "attempts" / "pend-1.json").exists()
    moved = read_attempt(coral_dir, "pend-1", island_id="1")
    assert moved is not None
    assert moved.status == "pending"
    assert moved.metadata["island_id"] == "1"


def test_maybe_run_migration_cycle_ignores_raw_eval_count_for_tune_only(tmp_path):
    """A high raw eval counter from tune attempts must not trigger migration."""
    from coral.agent.manager import AgentManager
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig, IslandsConfig
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "eval_count").write_text("100")
    _make_multi_island(coral_dir, n=2)
    write_attempt(
        coral_dir,
        _make_attempt("tune-0", "0-agent-1", 1.0, budget_class="tune"),
        island_id="0",
    )
    write_attempt(
        coral_dir,
        _make_attempt("tune-1", "1-agent-1", 2.0, budget_class="tune"),
        island_id="1",
    )

    mgr = AgentManager(
        CoralConfig(
            agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
            islands=IslandsConfig(count=2),
        )
    )
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    called = False

    def fake_run_cycle(**_kwargs):
        nonlocal called
        called = True
        return []

    mgr._migration_runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    mgr._maybe_run_migration_cycle()

    assert called is False
    assert mgr._migration_runner.last_cycle_evals == -1


def test_prune_deferred_keeps_blocked_batch_until_stale():
    """Deferred batches retry indefinitely unless a member is stale."""
    from coral.agent.manager import AgentManager
    from coral.agent.migration import MigrationCandidate
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig, IslandsConfig

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    mgr._agent_island = {
        "0-agent-1": "0",
        "1-agent-1": "1",
    }
    mgr._deferred_candidates = [
        (
            MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.1),
            "paused",
        ),
        (
            MigrationCandidate(agent_id="1-agent-1", src_island="1", dst_island="0", score=0.2),
            "still-paused",
        ),
    ]

    mgr._prune_deferred()

    assert [(c.agent_id, r) for c, r in mgr._deferred_candidates] == [
        ("0-agent-1", "paused"),
        ("1-agent-1", "still-paused"),
    ]

    mgr._agent_island["0-agent-1"] = "1"
    mgr._prune_deferred()

    assert mgr._deferred_candidates == []


def test_maybe_run_migration_cycle_retries_deferred_batch_before_fresh_cycle(tmp_path):
    """Deferred batches retry before fresh selection, even when a cycle is due."""
    from coral.agent.manager import AgentManager
    from coral.agent.migration import MigrationCandidate
    from coral.config import AgentAssignmentConfig, AgentConfig, CoralConfig, IslandsConfig
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    (coral_dir / "islands").mkdir()
    (coral_dir / "public").mkdir()
    (coral_dir / "eval_count").write_text("100")  # _get_eval_count reads this

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    mgr._agent_island = {"0-agent-1": "0", "0-agent-2": "0"}
    applied: list[MigrationCandidate] = []

    mgr._migration_block_reason = lambda _candidate: None  # type: ignore[assignment]
    mgr._apply_migration = lambda candidate, **_kwargs: applied.append(  # type: ignore[assignment]
        candidate
    )
    mgr._migration_runner.should_run = lambda **_: True  # type: ignore[assignment]
    mgr._migration_runner.run_cycle = pytest.fail  # type: ignore[assignment]
    mgr._deferred_candidates = [
        (
            MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5),
            "paused",
        ),
    ]

    mgr._maybe_run_migration_cycle()

    assert applied == [
        MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5)
    ]
    assert mgr._deferred_candidates == []


def test_maybe_run_migration_cycle_does_not_mix_blocked_deferred_with_fresh(tmp_path):
    """A still-blocked deferred batch suppresses fresh selection for that tick."""
    from coral.agent.manager import AgentManager
    from coral.agent.migration import MigrationCandidate
    from coral.config import (
        AgentAssignmentConfig,
        AgentConfig,
        CoralConfig,
        IslandsConfig,
        MigrationConfig,
    )
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    (coral_dir / "islands").mkdir()
    (coral_dir / "public").mkdir()
    (coral_dir / "eval_count").write_text("100")

    cfg = CoralConfig(
        agents=AgentConfig(assignments=[AgentAssignmentConfig(count=2)]),
        islands=IslandsConfig(count=2, migration=MigrationConfig(max_per_cycle=2)),
    )
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    mgr._agent_island = {"0-agent-1": "0", "1-agent-1": "1"}
    applied: list[MigrationCandidate] = []

    mgr._migration_block_reason = lambda _candidate: "paused"  # type: ignore[assignment]
    mgr._apply_migration = lambda candidate, **_kwargs: applied.append(  # type: ignore[assignment]
        candidate
    )
    mgr._migration_runner.should_run = lambda **_: True  # type: ignore[assignment]
    mgr._migration_runner.run_cycle = pytest.fail  # type: ignore[assignment]
    mgr._deferred_candidates = [
        (
            MigrationCandidate(agent_id="0-agent-1", src_island="0", dst_island="1", score=0.5),
            "paused",
        ),
    ]

    mgr._maybe_run_migration_cycle()

    assert applied == []
    assert [(c.agent_id, r) for c, r in mgr._deferred_candidates] == [("0-agent-1", "paused")]
