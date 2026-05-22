"""Commands: falsify, falsified, disputed.

These manage the team's "what doesn't work" list with a quorum + TTL gate
(see ``coral.hub.falsifications``).  An agent declares a topic dead by
running::

    coral falsify <slug> -m "evidence ..."

which writes a note under ``.coral/public/notes/`` with the right
frontmatter.  ``coral falsified`` lists topics that have ≥quorum distinct
agents claiming them.  ``coral disputed`` lists single-voice or expired
claims — the topics a future agent should consider re-testing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from coral.cli._helpers import find_coral_dir, read_agent_id
from coral.hub.attempts import read_eval_count
from coral.hub.falsifications import (
    TopicStatus,
    find_consensus,
    find_disputed,
    list_topics,
    validate_slug,
)


def _read_sharing_config(coral_dir: Path) -> tuple[int, int]:
    """Return (quorum, default_ttl) from ``coral_dir/config.yaml`` with sensible
    fallbacks (2 / 30) when missing.  Same yaml-parse pattern as
    ``read_direction()``."""
    quorum = 2
    ttl = 30
    config_path = coral_dir / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            cfg = {}
        sharing = (cfg.get("sharing") or {}) if isinstance(cfg, dict) else {}
        # Sub-config dict: sharing.falsification.{quorum,ttl_evals}
        falsification = (sharing.get("falsification") or {}) if isinstance(sharing, dict) else {}
        quorum = int(falsification.get("quorum", quorum) or quorum)
        ttl = int(falsification.get("ttl_evals", ttl) or ttl)
    return max(1, quorum), max(1, ttl)


def _slugify_filename(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "claim"


def cmd_falsify(args: argparse.Namespace) -> None:
    """Record this agent's "topic X is dead" claim.

    Writes a note under ``.coral/public/notes/falsified-<slug>-by-<agent>.md``
    with the right frontmatter so ``coral falsified`` / ``coral disputed`` /
    the CORAL.md template can pick it up.

    Examples:
      coral falsify xfmr-distill -m "ADD at w=0.04 → -0.00018, eval 28"
      coral falsify ssm-distill -m "val 0.66, ensemble drag"
    """
    slug = args.slug
    try:
        validate_slug(slug)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        print(
            "       Use lowercase letters/digits separated by single dashes, "
            "e.g. 'xfmr-distill-student'.",
            file=sys.stderr,
        )
        sys.exit(2)

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    agent_id = read_agent_id()
    if agent_id == "unknown":
        # The CLI can be invoked from a maintainer shell at the run root, in
        # which case we have no breadcrumb. Refuse rather than write an
        # uncountable claim (no creator → quorum can't see it).
        print(
            "error: cannot determine agent_id (no .coral_agent_id breadcrumb in cwd).\n"
            "       Run this from inside an agent worktree, or pass --as <agent-id>.",
            file=sys.stderr,
        )
        if not getattr(args, "as_agent", None):
            sys.exit(2)
        agent_id = args.as_agent

    quorum, default_ttl = _read_sharing_config(coral_dir)
    eval_count = read_eval_count(coral_dir)
    ttl = int(getattr(args, "ttl", None) or default_ttl)

    notes_dir = coral_dir / "public" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    filename = f"falsified-{_slugify_filename(slug)}-by-{_slugify_filename(agent_id)}.md"
    note_path = notes_dir / filename

    if note_path.exists() and not getattr(args, "force", False):
        print(
            f"error: a claim by {agent_id} on '{slug}' already exists at "
            f"{note_path.relative_to(coral_dir.parent)}.\n"
            "       Pass --force to overwrite (e.g. to refresh evidence and "
            "reset the TTL clock).",
            file=sys.stderr,
        )
        sys.exit(1)

    body = (args.message or "").strip()
    if not body:
        body = "(no evidence provided)"

    created = datetime.now(UTC).isoformat(timespec="seconds")
    content = (
        "---\n"
        f"creator: {agent_id}\n"
        f"created: {created}\n"
        f"falsifies: {slug}\n"
        f"claimed_at_eval: {eval_count}\n"
        f"ttl_evals: {ttl}\n"
        "---\n"
        "\n"
        f"# Falsifying {slug}\n"
        "\n"
        f"{body}\n"
    )
    note_path.write_text(content)

    # Tell the agent how the team will see this claim.
    matches = [
        s
        for s in list_topics(
            coral_dir,
            current_eval=eval_count,
            quorum=quorum,
            default_ttl=default_ttl,
        )
        if s.topic == slug
    ]
    status = matches[0] if matches else None

    print(f"Wrote claim to {note_path.relative_to(coral_dir.parent)}")
    if status:
        if status.level == "consensus":
            voices = ", ".join(status.voices)
            print(
                f"Status: CONSENSUS — quorum reached "
                f"({len(status.voices)}/{quorum}, voices: {voices})."
            )
        elif status.level == "disputed":
            print(
                f"Status: DISPUTED — {len(status.voices)}/{quorum} voices so "
                f"far. Need {quorum - len(status.voices)} more independent "
                "agent(s) to confirm."
            )
        elif status.level == "stale":
            # Shouldn't happen right after a write, but defensive.
            print("Status: STALE")


def cmd_falsified(args: argparse.Namespace) -> None:
    """List topics with team consensus (≥quorum agents claim them dead).

    Example:
      coral falsified
    """
    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    quorum, default_ttl = _read_sharing_config(coral_dir)
    eval_count = read_eval_count(coral_dir)

    topics = find_consensus(
        coral_dir,
        current_eval=eval_count,
        quorum=quorum,
        default_ttl=default_ttl,
    )
    if not topics:
        print(
            f"No topics have reached consensus yet "
            f"(quorum={quorum}, current eval={eval_count})."
        )
        return
    print(f"Team consensus dead-ends ({len(topics)} topic(s), quorum={quorum}):")
    _print_topic_table(topics, eval_count)


def cmd_disputed(args: argparse.Namespace) -> None:
    """List topics with disputed or stale claims — worth re-testing.

    Example:
      coral disputed
    """
    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    quorum, default_ttl = _read_sharing_config(coral_dir)
    eval_count = read_eval_count(coral_dir)

    topics = find_disputed(
        coral_dir,
        current_eval=eval_count,
        quorum=quorum,
        default_ttl=default_ttl,
    )
    if not topics:
        print(
            f"No disputed or stale claims (quorum={quorum}, "
            f"current eval={eval_count})."
        )
        return
    print(
        f"Disputed / stale claims ({len(topics)} topic(s), quorum={quorum}) — "
        "candidates for re-test:"
    )
    _print_topic_table(topics, eval_count)


def _print_topic_table(topics: list[TopicStatus], current_eval: int) -> None:
    """Plain-text table of topic statuses."""
    rows = [("Topic", "Status", "Voices", "All voices", "Expires", "Note(s)")]
    for s in topics:
        if s.level == "consensus" or s.level == "disputed":
            expires = (
                f"{s.expires_at_eval} "
                f"(in {max(0, s.expires_at_eval - current_eval)})"
            )
        else:  # stale
            expires = "expired"
        active = ", ".join(s.voices) or "—"
        all_v = ", ".join(s.all_voices) or "—"
        first_note = s.claims[0].note_path if s.claims else ""
        rows.append((s.topic, s.level, active, all_v, expires, first_note))

    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for i, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        print(line)
        if i == 0:
            print("  ".join("-" * w for w in widths))
