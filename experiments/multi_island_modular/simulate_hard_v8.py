#!/usr/bin/env python3
"""Deterministic treatment-sensitivity simulation for the v8 design.

This is not an agent-performance forecast. It models a compliant balanced
policy that shares certificates immediately within an island and carries the
best submitted certificate set across a migration. The simulator exists to
prove that the registered outcome is topology-blind before transfer and can
change only after a post-migration real submission.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

AGENTS = 8
LANES_PER_AGENT = 4
MODULE_COST = {"smooth": 34, "rugged": 1025}
MIGRATION_EVERY = {"smooth": 128, "rugged": 2048}
BUDGETS = {
    "smooth": (288, 384, 512, 768, 1024, 1536),
    "rugged": (8192, 10240, 12288, 16384, 24576, 32768, 40960),
}
CONDITIONS = ("global_8", "partition", "multi_island")


def _birth_island(agent: int, condition: str) -> int:
    return 0 if condition == "global_8" else agent % 2


def simulate(mode: str, condition: str, budget: int) -> dict[str, Any]:
    if mode not in MODULE_COST:
        raise ValueError(f"unknown mode {mode!r}")
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    if budget % AGENTS:
        raise ValueError("budget must divide evenly across eight agents")

    attempts = [0] * AGENTS
    island_knowledge: dict[int, set[int]] = {0: set()}
    if condition != "global_8":
        island_knowledge[1] = set()
    pending_arrival: dict[int, set[int]] = {island: set() for island in island_knowledge}
    discovery_origin: dict[int, int] = {}
    discovered: set[int] = set()
    best_submitted = 0
    cross_island_reuse: set[int] = set()
    first_cross_island_reuse: int | None = None
    migrations = 0

    for global_eval in range(1, budget + 1):
        agent = (global_eval - 1) % AGENTS
        island = _birth_island(agent, condition)
        attempts[agent] += 1

        # A migration makes a certificate package available, but the primary
        # submitted-artifact metric changes only when a later real attempt
        # actually carries and resubmits it.
        if pending_arrival[island]:
            island_knowledge[island].update(pending_arrival[island])
            pending_arrival[island].clear()

        module_number, remainder = divmod(attempts[agent], MODULE_COST[mode])
        if remainder == 0 and 1 <= module_number <= LANES_PER_AGENT:
            block = agent + AGENTS * (module_number - 1)
            island_knowledge[island].add(block)
            discovered.add(block)
            discovery_origin.setdefault(block, island)

        submitted = set(island_knowledge[island])
        foreign = {
            block
            for block in submitted
            if discovery_origin.get(block, island) != island
        }
        if foreign and first_cross_island_reuse is None:
            first_cross_island_reuse = global_eval
        cross_island_reuse.update(foreign)
        best_submitted = max(best_submitted, len(submitted))

        if (
            condition == "multi_island"
            and global_eval % MIGRATION_EVERY[mode] == 0
        ):
            left = set(island_knowledge[0])
            right = set(island_knowledge[1])
            pending_arrival[0].update(right)
            pending_arrival[1].update(left)
            migrations += 1

    per_island = {str(island): len(blocks) for island, blocks in island_knowledge.items()}
    return {
        "mode": mode,
        "condition": condition,
        "budget": budget,
        "best_submitted_certified_blocks": best_submitted,
        "global_discovered_blocks": len(discovered),
        "assembly_gap": len(discovered) - best_submitted,
        "per_island_known_blocks": per_island,
        "cross_island_reused_blocks": len(cross_island_reuse),
        "first_cross_island_reuse_eval": first_cross_island_reuse,
        "migration_cycles": migrations,
        "attempts_per_agent": attempts[0],
    }


def table() -> list[dict[str, Any]]:
    return [
        simulate(mode, condition, budget)
        for mode, budgets in BUDGETS.items()
        for budget in budgets
        for condition in CONDITIONS
    ]


def assert_treatment_sensitivity(rows: list[dict[str, Any]]) -> None:
    indexed = {
        (row["mode"], row["budget"], row["condition"]): row
        for row in rows
    }
    for mode, budgets in BUDGETS.items():
        for budget in budgets:
            partition = indexed[(mode, budget, "partition")]
            multi = indexed[(mode, budget, "multi_island")]
            if partition["cross_island_reused_blocks"] != 0:
                raise AssertionError("partition received an impossible cross-island union")
            if multi["best_submitted_certified_blocks"] > partition[
                "best_submitted_certified_blocks"
            ] and not multi["cross_island_reused_blocks"]:
                raise AssertionError("multi-island improved without submitted transfer")
            if partition["best_submitted_certified_blocks"] > partition[
                "global_discovered_blocks"
            ]:
                raise AssertionError("submitted assembly exceeds discovered knowledge")

    smooth_pre = indexed[("smooth", 384, "multi_island")]
    smooth_post = indexed[("smooth", 512, "multi_island")]
    smooth_partition = indexed[("smooth", 512, "partition")]
    if smooth_pre["cross_island_reused_blocks"] != 0:
        raise AssertionError("Smooth transfer occurred before a post-discovery migration")
    if smooth_post["best_submitted_certified_blocks"] <= smooth_partition[
        "best_submitted_certified_blocks"
    ]:
        raise AssertionError("Smooth registered ladder is not treatment-sensitive")

    rugged_pre = indexed[("rugged", 10240, "multi_island")]
    rugged_post = indexed[("rugged", 12288, "multi_island")]
    rugged_partition = indexed[("rugged", 12288, "partition")]
    if rugged_pre["cross_island_reused_blocks"] != 0:
        raise AssertionError("Rugged transfer occurred before a post-discovery migration")
    if rugged_post["best_submitted_certified_blocks"] <= rugged_partition[
        "best_submitted_certified_blocks"
    ]:
        raise AssertionError("Rugged registered ladder is not treatment-sensitive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = table()
    assert_treatment_sensitivity(rows)
    payload = {"schema_version": 1, "rows": rows}
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
