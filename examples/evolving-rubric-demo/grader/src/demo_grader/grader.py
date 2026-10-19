"""A deterministic, criteria-driven grader over ``answer.md``.

Each criterion's ``description`` ends with ``requires: <phrase>``; the criterion
scores 1.0 when the phrase appears in the artifact (case-insensitive), else 0.0.
The feedback lists, for every criterion, whether the phrase was found, and then
an **Observations** section naming properties of the artifact that no current
criterion covers. Those observations are what an evolving evaluator can turn
into new criteria: the demo proposer quotes one of them verbatim.
"""

from __future__ import annotations

import re
from pathlib import Path

from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle

#: Properties a reviewer might notice that the seed rubric does not check.
OBSERVATIONS = (
    ("code block", lambda t: "```" in t, "the artifact has no fenced code block"),
    ("section headings", lambda t: bool(re.search(r"^## ", t, re.M)), "the artifact has no section headings below the title"),
    ("numbers", lambda t: bool(re.search(r"\d", t)), "the artifact cites no numbers or measurements"),
    ("limitations", lambda t: "limitation" in t.lower(), "the artifact does not state its limitations"),
)


def requirement(description: str) -> str:
    m = re.search(r"requires:\s*(.+)$", description.strip(), re.I | re.S)
    return (m.group(1) if m else description).strip().lower()


class DemoGrader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        path = Path(self.codebase_path) / "answer.md"
        text = path.read_text(errors="replace") if path.is_file() else ""
        criteria = self.args.get("criteria") or []
        scores, lines = {}, []
        for c in criteria:
            phrase = requirement(c["description"])
            hit = phrase in text.lower()
            scores[c["name"]] = Score(value=1.0 if hit else 0.0, name=c["name"],
                                      explanation=f"{'found' if hit else 'missing'}: {phrase!r}")
            lines.append(f"- {c['name']}: {'PASS' if hit else 'FAIL'} ({'found' if hit else 'missing'} {phrase!r})")
        weights = {c["name"]: float(c.get("weight", 1.0)) for c in criteria}
        total = sum(weights.values()) or 1.0
        aggregated = sum(scores[n].value * weights[n] for n in scores) / total if scores else 0.0
        missing = [msg for _, pred, msg in OBSERVATIONS if not pred(text)]
        feedback = "## Criteria\n" + "\n".join(lines) + "\n\n## Observations\n" + (
            "\n".join(f"- {m}" for m in missing) if missing else "- nothing further noticed"
        )
        return ScoreBundle(scores=scores, aggregated=aggregated, feedback=feedback)
