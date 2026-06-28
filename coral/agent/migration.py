"""Island-migration: select a best agent on each source island and move it.

This module owns the *policy* (who is best, where do they go) and a thin
runner (``MigrationRunner``) that exposes the per-cycle cadence the manager
ticks against. The mechanics of actually swapping an agent onto a new
island — file moves, symlink repointing, restart prompt — live in the
manager (:mod:`coral.agent.manager`) because they touch the live agent
handle. The split keeps the policy code pure and trivially testable.

Migration semantics in one paragraph:

A migration cycle fires every ``MigrationConfig.every`` finalized real evals.
For each source island we look at its current residents (the live roster, not
historical attempt locations), rank each resident by the last
``rank_window`` *real* attempts it submitted on that island, and pick the
top-1 eligible resident per island. Each candidate is then assigned a
destination island under
``MigrationConfig.dest_weighting``: ``uniform`` (random non-source island),
``round_robin`` (deterministic shift by cycle index), or ``score`` (weight
each non-source island by its current best — higher attracts more migrants
under maximize, lower under minimize). The runner *never* picks the
source island as a destination. When the manager supplies a live roster,
the assigned candidates are reduced to the best subset of at most
``max_per_cycle`` moves that does not worsen the per-island agent-count
balance; from an already-balanced roster, that means migration happens as
a swap/cycle rather than as a one-way drain.

What moves with an agent (mechanics in the manager): ``roles/<agent>.md``,
``heartbeat/<agent>.json``, that agent's attempt records, and matching
``eval_logs/<commit>/`` directories follow them. Notes and skills authored
on the source island stay put as island-local shared knowledge. The agent's
worktree symlinks and ``.coral_island`` breadcrumb are repointed at the
destination, and an optional arrival note is dropped on the destination's
``notes/`` when ``notify_island=True`` so other agents see the newcomer
through ``coral notes``.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from coral.config import IslandsConfig
from coral.hub.attempts import read_attempts
from coral.types import BUDGET_CLASS_REAL, Attempt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationCandidate:
    """One agent's planned migration: src → dst, with the score that earned it.

    Frozen so the runner can return a set-friendly value that callers may
    dedup. ``score`` is the aggregated value used for selection (max over
    the last ``rank_window`` real attempts on the source island), retained
    on the candidate so the manager can log it and drop it into the
    arrival note.
    """

    agent_id: str
    src_island: str
    dst_island: str
    score: float


@dataclass(frozen=True)
class IslandRoster:
    """Current live-agent membership for a multi-island run.

    This is deliberately separate from attempt storage. Current code moves
    attempt records with the agent, but old runs or partial failures may still
    leave records behind; the roster is the source of truth for where each live
    agent belongs now.
    """

    agent_islands: dict[str, str]
    island_ids: tuple[str, ...]
    target_counts: dict[str, int]

    @classmethod
    def from_agent_islands(
        cls,
        agent_islands: dict[str, str],
        *,
        island_ids: list[str],
    ) -> IslandRoster:
        ids = tuple(island_ids)
        targets = _balanced_target_counts(ids, len(agent_islands))
        return cls(agent_islands=dict(agent_islands), island_ids=ids, target_counts=targets)

    def current_island(self, agent_id: str) -> str | None:
        return self.agent_islands.get(agent_id)

    def is_on(self, agent_id: str, island_id: str) -> bool:
        return self.current_island(agent_id) == island_id

    def counts(self) -> dict[str, int]:
        counts = {island_id: 0 for island_id in self.island_ids}
        for island_id in self.agent_islands.values():
            if island_id in counts:
                counts[island_id] += 1
        return counts


def score_for_agent(
    attempts: Iterable[Attempt],
    *,
    rank_window: int,
    minimize: bool,
) -> float | None:
    """Aggregate an agent's score over its last ``rank_window`` *real* attempts.

    Attempts are sorted by timestamp ascending; only the trailing
    ``rank_window`` real-mode entries with a non-None score are considered.
    Returns ``min`` for ``minimize=True``, otherwise ``max``. Returns
    ``None`` if the agent has zero real scored attempts in the window.

    The caller is expected to pre-filter ``attempts`` to a single agent —
    no agent_id check happens here, so the function works equally well as
    a "best score in a window" primitive in tests.
    """
    eligible = [a for a in attempts if a.budget_class == BUDGET_CLASS_REAL and a.score is not None]
    if not eligible:
        return None
    eligible.sort(key=lambda a: a.timestamp)
    window = eligible[-rank_window:]
    scores = [a.score for a in window if a.score is not None]
    if not scores:
        return None
    return min(scores) if minimize else max(scores)


def select_candidates(
    coral_dir: str | Path,
    *,
    island_ids: list[str],
    rank_window: int,
    min_evals: int,
    minimize: bool,
    roster: IslandRoster | None = None,
    current_agent_islands: dict[str, str] | None = None,
) -> list[MigrationCandidate]:
    """For each source island, return its best eligible agent (at most one).

    Eligibility:
      * The agent has ``>= min_evals`` *real* attempts on the source
        island (tune / grader_error attempts don't count toward the
        threshold). This both protects newcomers from being yanked out
        too early and ensures the score aggregation has signal.
      * When a roster is provided, the agent currently lives on this
        source island. Attempt directories are historical evidence, not
        membership truth.
      * The agent has at least one real attempt with a non-None score in
        the trailing ``rank_window`` — otherwise we'd have no score to
        rank by.

    Returns a candidate per island (or none for islands with no eligible
    agent), each with ``dst_island = ""`` for the assignment step to fill in.
    """
    candidates: list[MigrationCandidate] = []
    if roster is None and current_agent_islands is not None:
        roster = IslandRoster.from_agent_islands(
            current_agent_islands,
            island_ids=island_ids,
        )
    for src in island_ids:
        attempts = read_attempts(coral_dir, island_id=src)
        per_agent: dict[str, list[Attempt]] = {}
        for a in attempts:
            per_agent.setdefault(a.agent_id, []).append(a)

        best_agent: str | None = None
        best_score: float | None = None
        for agent_id, agent_attempts in per_agent.items():
            if roster is not None and not roster.is_on(agent_id, src):
                continue
            real = [a for a in agent_attempts if a.budget_class == BUDGET_CLASS_REAL]
            if len(real) < min_evals:
                continue
            score = score_for_agent(agent_attempts, rank_window=rank_window, minimize=minimize)
            if score is None:
                continue
            if best_score is None or ((score < best_score) if minimize else (score > best_score)):
                best_agent = agent_id
                best_score = score

        if best_agent is not None and best_score is not None:
            candidates.append(
                MigrationCandidate(
                    agent_id=best_agent,
                    src_island=src,
                    dst_island="",
                    score=best_score,
                )
            )
    return candidates


def assign_destinations(
    candidates: list[MigrationCandidate],
    *,
    island_ids: list[str],
    weighting: str,
    cycle_idx: int,
    island_best_scores: dict[str, float],
    rng: random.Random,
    minimize: bool,
) -> list[MigrationCandidate]:
    """Stamp each candidate with a destination island, honoring the policy.

    Guarantees ``dst_island != src_island`` for every returned candidate.
    Returns an empty list if there is no legal destination (i.e. only one
    island exists), so single-island accidents degrade gracefully.

    Policies:
        ``uniform`` — uniform random over non-source islands.
        ``round_robin`` — deterministic shift: each candidate lands on
            ``island_ids[(src_index + cycle_idx + offset) % count]`` where
            ``offset`` is bumped until the result differs from src. Per-cycle
            ``cycle_idx`` is used so subsequent cycles vary even with
            identical candidates.
        ``score`` — weight each non-source island by its current best
            score. Under ``minimize=False``, higher score → higher weight
            (rich-get-richer); under ``minimize=True``, lower score →
            higher weight. Falls back to uniform when no island_best_scores
            are recorded yet (typical early in a run).
    """
    if len(island_ids) <= 1:
        return []

    assigned: list[MigrationCandidate] = []
    for candidate in candidates:
        non_src = [i for i in island_ids if i != candidate.src_island]
        if not non_src:
            continue  # defensive — shouldn't happen given the count check above

        if weighting == "round_robin":
            try:
                src_idx = island_ids.index(candidate.src_island)
            except ValueError:
                src_idx = 0
            offset = 1
            n = len(island_ids)
            while True:
                dst_idx = (src_idx + cycle_idx + offset) % n
                dst = island_ids[dst_idx]
                if dst != candidate.src_island:
                    break
                offset += 1
        elif weighting == "uniform":
            dst = rng.choice(non_src)
        elif weighting == "score":
            weights = _score_weights(non_src, island_best_scores, minimize=minimize)
            if weights is None:
                # No score signal yet — uniform is the only honest fallback.
                dst = rng.choice(non_src)
            else:
                dst = rng.choices(non_src, weights=weights, k=1)[0]
        else:
            # Unknown weighting is normally rejected by MigrationConfig
            # validation; raise here too so a misconfigured runner is loud.
            raise ValueError(f"unknown dest_weighting: {weighting!r}")

        assigned.append(
            MigrationCandidate(
                agent_id=candidate.agent_id,
                src_island=candidate.src_island,
                dst_island=dst,
                score=candidate.score,
            )
        )
    return assigned


def _score_weights(
    islands: list[str],
    best_scores: dict[str, float],
    *,
    minimize: bool,
) -> list[float] | None:
    """Convert per-island best scores into ``random.choices`` weights.

    Returns ``None`` if no listed island has a recorded score (no signal —
    caller should fall back to uniform). Otherwise produces a weight per
    island; islands without a recorded score get the minimum positive
    weight in the batch so they remain reachable. Under ``minimize=True``
    weights are inverted (lower score → higher weight) by reflecting
    around ``max + min - score``.
    """
    raw: list[tuple[str, float | None]] = [(i, best_scores.get(i)) for i in islands]
    known = [s for _, s in raw if s is not None]
    if not known:
        return None

    if minimize:
        # Reflect around the max so lower scores end up with higher weights.
        # Add a tiny floor so the highest score (smallest weight here) is
        # still reachable instead of dropping to 0.
        max_s = max(known)
        transformed = [(i, (max_s - s + 1e-9) if s is not None else None) for i, s in raw]
    else:
        # Shift so the smallest score still has a strictly positive weight.
        min_s = min(known)
        offset = -min_s + 1e-9 if min_s <= 0 else 0.0
        transformed = [(i, (s + offset) if s is not None else None) for i, s in raw]

    # Islands with no recorded score get the minimum positive weight in the
    # batch so they remain reachable but not preferred over scored islands.
    positive = [w for _, w in transformed if w is not None and w > 0]
    fallback = min(positive) if positive else 1e-9
    return [w if w is not None else fallback for _, w in transformed]


def choose_roster_balanced_subset(
    candidates: list[MigrationCandidate],
    *,
    roster: IslandRoster,
    max_per_cycle: int,
    minimize: bool,
) -> list[MigrationCandidate]:
    """Choose the best candidate subset without worsening roster balance.

    Because migration *moves* an agent, a one-way migration from an already
    balanced roster necessarily drains one island and overloads another. This
    chooser therefore accepts only subsets whose post-migration counts are no
    farther from the balanced target than the current counts. If the run is
    already imbalanced, a one-way migration is allowed when it reduces that
    imbalance.
    """
    if max_per_cycle <= 0 or not candidates:
        return []

    current_counts = roster.counts()
    start_deviation = _count_deviation(current_counts, roster.target_counts)
    limit = min(max_per_cycle, len(candidates))

    best_subset: tuple[MigrationCandidate, ...] = ()
    best_key = (-start_deviation, 0, 0.0)
    for size in range(1, limit + 1):
        for subset in combinations(candidates, size):
            if len({c.agent_id for c in subset}) != len(subset):
                continue
            post_counts = _counts_after(current_counts, subset)
            if post_counts is None:
                continue
            deviation = _count_deviation(post_counts, roster.target_counts)
            if deviation > start_deviation:
                continue
            score_signal = sum((-c.score if minimize else c.score) for c in subset)
            key = (-deviation, len(subset), score_signal)
            if key > best_key:
                best_key = key
                best_subset = subset

    return list(best_subset)


def _balanced_target_counts(island_ids: tuple[str, ...], total_agents: int) -> dict[str, int]:
    if not island_ids:
        return {}
    base, remainder = divmod(total_agents, len(island_ids))
    return {
        island_id: base + (1 if idx < remainder else 0) for idx, island_id in enumerate(island_ids)
    }


def _count_deviation(counts: dict[str, int], targets: dict[str, int]) -> int:
    island_ids = set(counts) | set(targets)
    return sum(abs(counts.get(i, 0) - targets.get(i, 0)) for i in island_ids)


def _counts_after(
    counts: dict[str, int],
    migrations: Iterable[MigrationCandidate],
) -> dict[str, int] | None:
    post = dict(counts)
    for candidate in migrations:
        if post.get(candidate.src_island, 0) <= 0:
            return None
        post[candidate.src_island] = post.get(candidate.src_island, 0) - 1
        post[candidate.dst_island] = post.get(candidate.dst_island, 0) + 1
    return post


class MigrationRunner:
    """Per-run migration coordinator.

    Holds the cross-cycle state (``last_cycle_evals``, cycle counter, RNG)
    so the policy functions above can stay pure. The manager constructs
    one of these in ``start_all``/``resume_all`` and calls ``should_run``
    on each finalized real-attempt tick; when it fires, the manager calls
    ``run_cycle`` to get the planned migrations, applies each via its own
    file/process mechanics, then calls ``mark_cycle_complete``.
    """

    def __init__(
        self,
        islands_config: IslandsConfig,
        *,
        minimize: bool,
        rng: random.Random | None = None,
    ) -> None:
        self.islands_config = islands_config
        self.migration_config = islands_config.migration
        self.minimize = minimize
        self.rng = rng if rng is not None else random.Random()
        # Negative so the first crossing of `every` always fires regardless
        # of where the global counter happens to start (e.g. after a resume).
        self.last_cycle_evals: int = -1
        self.cycle_idx: int = 0

    @property
    def enabled(self) -> bool:
        """A migration runner is meaningful only with >=2 islands and migration on."""
        return self.islands_config.count > 1 and self.migration_config.enabled

    def should_run(self, *, current_global_evals: int) -> bool:
        """True iff we've crossed an ``every`` boundary since the last cycle."""
        if not self.enabled:
            return False
        if current_global_evals <= 0:
            return False
        if self.last_cycle_evals < 0:
            return current_global_evals >= self.migration_config.every
        return current_global_evals - self.last_cycle_evals >= self.migration_config.every

    def mark_cycle_complete(self, *, current_global_evals: int) -> None:
        """Record that we just ran a cycle; bumps the cycle counter for round_robin."""
        self.last_cycle_evals = current_global_evals
        self.cycle_idx += 1

    def run_cycle(
        self,
        *,
        coral_dir: str | Path,
        island_best_scores: dict[str, float],
        current_agent_islands: dict[str, str] | None = None,
    ) -> list[MigrationCandidate]:
        """Plan one migration cycle. Caller applies the returned candidates.

        ``island_best_scores`` is a snapshot of each island's current best
        score (typically the per-island leaderboard top), used by the
        ``score`` destination policy. Pass an empty dict in single-cycle
        unit tests to exercise the uniform fallback.

        Returns up to ``max_per_cycle`` candidates, each with a non-empty
        ``dst_island``. Returns an empty list when:
            * No island has an eligible agent (everyone is below
              ``min_evals``, or no real scored attempts exist).
            * ``count == 1`` (no destinations).
            * The runner is disabled.
        """
        if not self.enabled:
            return []

        coral_dir = Path(coral_dir)
        island_ids = _discover_island_ids(coral_dir, expected_count=self.islands_config.count)
        if len(island_ids) <= 1:
            return []
        roster = (
            IslandRoster.from_agent_islands(current_agent_islands, island_ids=island_ids)
            if current_agent_islands is not None
            else None
        )

        raw = select_candidates(
            coral_dir,
            island_ids=island_ids,
            rank_window=self.migration_config.rank_window,
            min_evals=self.migration_config.min_evals,
            minimize=self.minimize,
            roster=roster,
        )
        if not raw:
            return []

        # When there are more candidates than ``max_per_cycle`` slots, prefer
        # the ones with the strongest source score (in the grader's direction).
        raw.sort(key=lambda c: c.score, reverse=not self.minimize)
        if roster is None:
            raw = raw[: self.migration_config.max_per_cycle]

        assigned = assign_destinations(
            raw,
            island_ids=island_ids,
            weighting=self.migration_config.dest_weighting,
            cycle_idx=self.cycle_idx,
            island_best_scores=island_best_scores,
            rng=self.rng,
            minimize=self.minimize,
        )
        if roster is None:
            return assigned
        selected = choose_roster_balanced_subset(
            assigned,
            roster=roster,
            max_per_cycle=self.migration_config.max_per_cycle,
            minimize=self.minimize,
        )
        if assigned and not selected:
            logger.info(
                "Migration cycle skipped %d candidate(s) to preserve island roster balance",
                len(assigned),
            )
        return selected


def _discover_island_ids(coral_dir: Path, *, expected_count: int) -> list[str]:
    """Return on-disk island ids, sorted. Falls back to range(expected_count) if none on disk.

    Multi-island layouts always have ``coral_dir/islands/<id>/`` on disk by
    the time the manager constructs the runner; the fallback is a safety
    net for first-cycle calls happening before any island dirs exist
    (mostly in tests).
    """
    islands_dir = coral_dir / "islands"
    if islands_dir.exists():
        ids = sorted(d.name for d in islands_dir.iterdir() if d.is_dir())
        if ids:
            return ids
    return [str(i) for i in range(expected_count)]
