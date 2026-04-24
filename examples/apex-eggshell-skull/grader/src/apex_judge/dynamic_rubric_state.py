"""Rubric versioning and persistence for the agent-judge grader.

Stores versioned rubric snapshots in .coral/private/rubrics/ and tracks
which rubric version was used for each attempt.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apex_judge.rubric_item import RubricItem

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class RubricVersion:
    """A versioned snapshot of the rubric criteria."""

    version: int
    rubrics: list[RubricItem]
    retired: list[RubricItem] = field(default_factory=list)
    created_at: str = ""
    trigger: str = "initial"  # "initial" | "periodic" | "plateau" | "judge"
    evolution_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "rubrics": [
                {"name": r.name, "description": r.description, "weight": r.weight}
                for r in self.rubrics
            ],
            "retired": [
                {"name": r.name, "description": r.description, "weight": r.weight}
                for r in self.retired
            ],
            "created_at": self.created_at,
            "trigger": self.trigger,
            "evolution_notes": self.evolution_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricVersion:
        return cls(
            version=data["version"],
            rubrics=[
                RubricItem(name=r["name"], description=r["description"], weight=r.get("weight", 1.0))
                for r in data.get("rubrics", [])
            ],
            retired=[
                RubricItem(name=r["name"], description=r["description"], weight=r.get("weight", 1.0))
                for r in data.get("retired", [])
            ],
            created_at=data.get("created_at", ""),
            trigger=data.get("trigger", "initial"),
            evolution_notes=data.get("evolution_notes", ""),
        )


class RubricStateManager:
    """Manages versioned rubric state in .coral/private/rubrics/."""

    def __init__(self, private_dir: str | Path) -> None:
        self._rubrics_dir = Path(private_dir) / "rubrics"
        self._rubrics_dir.mkdir(parents=True, exist_ok=True)

    def get_current_version(self) -> RubricVersion | None:
        """Load the current rubric version, or None if no rubrics exist yet."""
        current = self._rubrics_dir / "current.json"
        if not current.exists():
            return None
        try:
            data = json.loads(current.read_text())
            return RubricVersion.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def save_version(self, version: RubricVersion, task_name: str = "") -> Path:
        """Save a rubric version atomically. Writes v{N}.json and updates current.json."""
        if not version.created_at:
            version.created_at = datetime.now(UTC).isoformat()

        data = json.dumps(version.to_dict(), indent=2)

        versioned = self._rubrics_dir / f"v{version.version}.json"
        self._atomic_write(versioned, data)

        self._atomic_write(self._rubrics_dir / "current.json", data)

        self._append_changelog(version, task_name=task_name)

        return versioned

    def get_version(self, n: int) -> RubricVersion | None:
        """Load a specific rubric version by number."""
        path = self._rubrics_dir / f"v{n}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return RubricVersion.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def list_versions(self) -> list[int]:
        """List all saved version numbers, sorted ascending."""
        versions = []
        for f in self._rubrics_dir.glob("v*.json"):
            try:
                versions.append(int(f.stem[1:]))
            except ValueError:
                continue
        return sorted(versions)

    def should_evolve(
        self,
        eval_count: int,
        recent_scores: list[float],
        evolve_every: int = 5,
        plateau_threshold: int = 3,
    ) -> tuple[bool, str]:
        """Check whether rubrics should evolve. Returns (should_evolve, trigger_reason)."""
        if evolve_every > 0 and eval_count > 0 and eval_count % evolve_every == 0:
            return True, "periodic"

        if plateau_threshold > 0 and len(recent_scores) >= plateau_threshold:
            last_n = recent_scores[-plateau_threshold:]
            if len(set(round(s, 6) for s in last_n)) == 1:
                return True, "plateau"
            if all(last_n[i] >= last_n[i + 1] for i in range(len(last_n) - 1)):
                best_before = (
                    max(recent_scores[:-plateau_threshold])
                    if len(recent_scores) > plateau_threshold
                    else 0.0
                )
                if last_n[-1] <= best_before:
                    return True, "plateau"

        return False, ""

    def was_last_eval_perfect(self) -> bool:
        """Check whether the most recent evaluation had all criteria PASS."""
        history_path = self._rubrics_dir / "criterion_history.jsonl"
        if not history_path.exists():
            return False

        last_line = ""
        for line in history_path.read_text().splitlines():
            line = line.strip()
            if line:
                last_line = line

        if not last_line:
            return False

        try:
            entry = json.loads(last_line)
        except json.JSONDecodeError:
            return False

        criteria = entry.get("criteria", {})
        if not criteria:
            return False

        return all(c.get("verdict") == "PASS" for c in criteria.values())

    def record_criterion_scores(
        self,
        attempt_hash: str,
        rubric_version: int,
        criteria_scores: dict[str, dict[str, Any]],
    ) -> None:
        """Append per-criterion results to criterion_history.jsonl."""
        history_path = self._rubrics_dir / "criterion_history.jsonl"
        entry = {
            "attempt": attempt_hash,
            "rubric_version": rubric_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "criteria": criteria_scores,
        }
        with open(history_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_criterion_summary(self, last_n: int = 10) -> str:
        """Compute per-criterion stats from recent evaluations."""
        history_path = self._rubrics_dir / "criterion_history.jsonl"
        if not history_path.exists():
            return "No evaluation history available yet."

        entries: list[dict[str, Any]] = []
        for line in history_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not entries:
            return "No evaluation history available yet."

        entries = entries[-last_n:]

        criterion_data: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            for name, data in entry.get("criteria", {}).items():
                criterion_data.setdefault(name, []).append(data)

        lines = []
        for name, records in sorted(criterion_data.items()):
            passes = sum(1 for r in records if r.get("verdict") == "PASS")
            total = len(records)
            pass_rate = passes / total if total > 0 else 0.0

            if total >= 4:
                mid = total // 2
                first_half = sum(1 for r in records[:mid] if r.get("verdict") == "PASS") / mid
                second_half = sum(
                    1 for r in records[mid:] if r.get("verdict") == "PASS"
                ) / (total - mid)
                if second_half > first_half + 0.15:
                    trend = "improving"
                elif second_half < first_half - 0.15:
                    trend = "declining"
                else:
                    trend = "stable"
            else:
                trend = "insufficient data"

            fail_rationale = ""
            for r in reversed(records):
                if r.get("verdict") == "FAIL" and r.get("rationale"):
                    fail_rationale = r["rationale"][:200]
                    break

            line = f'- "{name}": {passes}/{total} passed ({pass_rate:.0%}, {trend})'
            if fail_rationale:
                line += f' — last failure: "{fail_rationale}"'
            lines.append(line)

        return "\n".join(lines)

    def publish_rubric(self, public_dir: str | Path) -> Path:
        """Write a human-readable current.md to the public rubrics directory."""
        current = self.get_current_version()
        if current is None:
            raise RuntimeError("No rubric version to publish")

        rubrics_public = Path(public_dir) / "rubrics"
        rubrics_public.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Evaluation Rubric (v{current.version})",
            "",
            f"Last updated: {current.created_at}",
            "",
            "## Active Criteria",
            "",
        ]
        for i, r in enumerate(current.rubrics, 1):
            lines.append(f"{i}. **{r.name}** (weight: {r.weight})")
            lines.append(f"   {r.description}")
            lines.append("")

        if current.retired:
            lines.append("## Recently Retired")
            lines.append("")
            for r in current.retired:
                lines.append(f"- ~~{r.name}~~ (weight: {r.weight})")
            lines.append("")

        if current.evolution_notes:
            lines.append("## Evolution Notes")
            lines.append("")
            lines.append(current.evolution_notes)
            lines.append("")

        out_path = rubrics_public / "current.md"
        self._atomic_write(out_path, "\n".join(lines))
        return out_path

    def record_attempt_version(self, commit_hash: str, version: int) -> None:
        """Record which rubric version was used for an attempt."""
        mapping = self._load_attempt_versions()
        mapping[commit_hash] = version
        self._atomic_write(
            self._rubrics_dir / "attempt_versions.json",
            json.dumps(mapping, indent=2),
        )

    def get_attempt_version(self, commit_hash: str) -> int | None:
        """Get the rubric version used for a specific attempt."""
        mapping = self._load_attempt_versions()
        return mapping.get(commit_hash)

    def _load_attempt_versions(self) -> dict[str, int]:
        path = self._rubrics_dir / "attempt_versions.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, KeyError):
            return {}

    def _append_changelog(self, version: RubricVersion, task_name: str = "") -> None:
        """Append an entry to the rubric changelog markdown file."""
        changelog = self._rubrics_dir / "RUBRIC_CHANGELOG.md"

        if not changelog.exists():
            template_path = _TEMPLATES_DIR / "rubric_changelog.md.template"
            if template_path.exists():
                header = template_path.read_text().format(
                    task_name=task_name or "Unknown",
                    start_time=version.created_at or datetime.now(UTC).isoformat(),
                )
            else:
                header = (
                    "# Rubric Evolution Changelog\n\n"
                    "This file tracks all changes to the evaluation rubrics over time.\n\n"
                    "---\n\n"
                )
            changelog.write_text(header)

        entry_lines = [f"## Version {version.version}"]
        entry_lines.append(f"- **Created:** {version.created_at}")
        entry_lines.append(f"- **Trigger:** {version.trigger}")
        if version.evolution_notes:
            entry_lines.append(f"- **Notes:** {version.evolution_notes}")

        entry_lines.append("")
        entry_lines.append("### Active Criteria")
        for r in version.rubrics:
            entry_lines.append(f"- **{r.name}** (weight: {r.weight}): {r.description}")

        if version.retired:
            entry_lines.append("")
            entry_lines.append("### Retired Criteria")
            for r in version.retired:
                entry_lines.append(f"- ~~{r.name}~~: {r.description}")

        entry_lines.append("")
        entry_lines.append("---\n")

        with open(changelog, "a") as f:
            f.write("\n".join(entry_lines))

    @staticmethod
    def _atomic_write(path: Path, data: str) -> None:
        """Write data to a file atomically via temp file + rename."""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, suffix=".tmp", delete=False
        )
        try:
            tmp.write(data)
            tmp.flush()
            tmp.close()
            Path(tmp.name).rename(path)
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise
