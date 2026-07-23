"""Policy-level ablation for island-migration: remigration cooldown + dest
strategy comparison.

Drives the *real* migration policy code (MigrationRunner, select_candidates,
assign_destinations) against real on-disk attempt records, with a synthetic
score process standing in for LLM agents:

- all islands share one baseline (CORAL islands run the same grader, so there
  is no environmental ceiling difference — weakness is emergent, not niche);
- agents have *persistent* talent differences (the elite stays elite);
- skill grows slowly toward a high cap (hard to reach within the budget) and
  migration keeps only 30% (heavy re-orientation cost);
- knowledge diffusion: a migrant lifts every teammate on the destination
  island by a small permanent skill bump — this is the channel migration is
  supposed to help through (spread strong genes), and the axis where dest
  strategies (score=rich-get-richer vs weakest=rescue) should differ.

Metrics compare cooldown x dest_weighting arms:
- ping-pong migrations (cooldown's job),
- final inter-island best-score spread (dest strategy's job: weakest should
  narrow it, score should widen it),
- global best (structurally migration is a net skill loss here, so no dest
  strategy is expected to move the peak — reported for completeness).

This validates mechanism-level claims only; it is NOT evidence about real
LLM agent runs.
"""

from __future__ import annotations

import random
import shutil
import statistics
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from coral.agent.migration import MigrationRunner
from coral.config import IslandsConfig, MigrationConfig
from coral.hub.attempts import read_attempts, write_attempt
from coral.types import Attempt

N_ISLANDS = 4
AGENTS_PER_ISLAND = 2
TOTAL_EVALS = 600
EVERY = 50
SKILL_GAIN = 0.005
SKILL_CAP = 1.5
MIGRATION_SKILL_KEEP = 0.3
DIFFUSION_GAIN = 0.04
BASELINE = 0.5
NOISE = 0.05


def run_arm(*, cooldown: int, dest_weighting: str, seed: int) -> dict:
    rng = random.Random(seed)
    tmp = tempfile.TemporaryDirectory()
    coral_dir = Path(tmp.name)
    for i in range(N_ISLANDS):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)

    mig = MigrationConfig(
        every=EVERY,
        rank_window=20,
        min_evals=3,
        max_per_cycle=2,
        dest_weighting=dest_weighting,
        remigration_cooldown=cooldown,
    )
    runner = MigrationRunner(
        IslandsConfig(count=N_ISLANDS, migration=mig),
        minimize=False,
        rng=random.Random(seed),
    )

    agents = [f"agent-{i}-{j}" for i in range(N_ISLANDS) for j in range(AGENTS_PER_ISLAND)]
    island_of = {
        f"agent-{i}-{j}": str(i) for i in range(N_ISLANDS) for j in range(AGENTS_PER_ISLAND)
    }
    skill = {a: 0.0 for a in agents}
    talent = {a: rng.uniform(0.7, 1.3) for a in agents}
    cap_of = {a: SKILL_CAP * talent[a] for a in agents}

    last_migrated: dict[str, int] = {}
    migrated_in_cycle: dict[str, int] = {}
    cycle_idx = 0
    pingpong = 0
    total_migrations = 0
    distinct_migrants: set[str] = set()
    best_curve: list[float] = []
    global_best = 0.0
    commit_n = 0
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    for ev in range(1, TOTAL_EVALS + 1):
        a = rng.choice(agents)
        skill[a] = min(cap_of[a], skill[a] + SKILL_GAIN * talent[a])
        score = max(0.0, BASELINE + skill[a] + rng.gauss(0, NOISE))
        global_best = max(global_best, score)
        best_curve.append(global_best)
        commit_n += 1
        write_attempt(
            coral_dir,
            Attempt(
                commit_hash=f"c{commit_n:06d}",
                agent_id=a,
                title="sim",
                score=score,
                status="improved",
                parent_hash=None,
                timestamp=(t0 + timedelta(seconds=ev)).isoformat(),
            ),
            island_id=island_of[a],
        )

        if not runner.should_run(current_global_evals=ev):
            continue
        island_best = {}
        for i in range(N_ISLANDS):
            scores = [
                at.score
                for at in read_attempts(coral_dir, island_id=str(i))
                if at.score is not None
            ]
            if scores:
                island_best[str(i)] = max(scores)
        migrations = runner.run_cycle(
            coral_dir=coral_dir,
            island_best_scores=island_best,
            current_agent_islands=dict(island_of),
            last_migrated_evals=last_migrated,
            current_evals=ev,
        )
        runner.mark_cycle_complete(current_global_evals=ev)
        cycle_idx += 1

        for c in migrations:
            a = c.agent_id
            if migrated_in_cycle.get(a) == cycle_idx - 1:
                pingpong += 1
            migrated_in_cycle[a] = cycle_idx
            distinct_migrants.add(a)
            total_migrations += 1
            # Knowledge diffusion: the migrant lifts every teammate already
            # on the destination island.
            for other in agents:
                if other != a and island_of[other] == c.dst_island:
                    skill[other] = min(cap_of[other], skill[other] + DIFFUSION_GAIN)
            # Manager mechanics: attempt records move with the agent.
            src_dir = coral_dir / "islands" / c.src_island / "attempts"
            dst_dir = coral_dir / "islands" / c.dst_island / "attempts"
            for f in src_dir.glob("*.json"):
                shutil.move(str(f), dst_dir / f.name)
            island_of[a] = c.dst_island
            last_migrated[a] = ev
            skill[a] *= MIGRATION_SKILL_KEEP

    # Final inter-island best-score spread (pstdev across islands).
    final_island_best = []
    for i in range(N_ISLANDS):
        scores = [
            at.score for at in read_attempts(coral_dir, island_id=str(i)) if at.score is not None
        ]
        final_island_best.append(max(scores) if scores else 0.0)
    inter_island_spread = statistics.pstdev(final_island_best)

    tmp.cleanup()
    return {
        "final_best": global_best,
        "auc_best": statistics.fmean(best_curve),
        "pingpong": pingpong,
        "migrations": total_migrations,
        "distinct_migrants": len(distinct_migrants),
        "island_spread": inter_island_spread,
    }


def main() -> None:
    seeds = range(8)
    arms = [
        ("cooldown=0,uniform (old)", dict(cooldown=0, dest_weighting="uniform")),
        ("cooldown=100,uniform", dict(cooldown=100, dest_weighting="uniform")),
        ("cooldown=100,score", dict(cooldown=100, dest_weighting="score")),
        ("cooldown=100,weakest", dict(cooldown=100, dest_weighting="weakest")),
    ]
    print(
        f"{'arm':<28} {'final_best':>16} {'auc_best':>16} {'island_spread':>16} "
        f"{'pingpong':>9} {'distinct':>9}"
    )
    for name, kw in arms:
        rows = [run_arm(seed=s, **kw) for s in seeds]
        keys = ["final_best", "auc_best", "island_spread", "pingpong", "distinct_migrants"]
        means = {k: statistics.fmean(r[k] for r in rows) for k in keys}
        stds = {k: statistics.pstdev(r[k] for r in rows) for k in keys}
        print(
            f"{name:<28} {means['final_best']:>10.3f}±{stds['final_best']:.3f} "
            f"{means['auc_best']:>10.3f}±{stds['auc_best']:.3f} "
            f"{means['island_spread']:>10.3f}±{stds['island_spread']:.3f} "
            f"{means['pingpong']:>4.1f}±{stds['pingpong']:.1f} "
            f"{means['distinct_migrants']:>5.2f}±{stds['distinct_migrants']:.2f}"
        )


if __name__ == "__main__":
    main()
