#!/usr/bin/env python3
"""A scripted stand-in for the proposer model, for the offline demo and tests.

Reads the prompt on stdin (ignored except as a signal), then reads the staged
evidence directory it was started in exactly as the real proposer would:
``attempts/<id>/feedback.md`` for each recent attempt. It proposes one criterion
for the first **Observation** it finds, quoting that observation verbatim from
the feedback so the grounding gate passes, and phrases the description in the
``requires: <phrase>`` form the demo grader scores. Prints the proposal JSON.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIREMENT = {
    "the artifact has no fenced code block": ("Code Example", "requires: ```"),
    "the artifact has no section headings below the title": ("Sectioned Structure", "requires: ## "),
    "the artifact cites no numbers or measurements": ("Quantified Claims", "requires: 0"),
    "the artifact does not state its limitations": ("States Limitations", "requires: limitation"),
}


def main() -> int:
    sys.stdin.read()
    proposals = []
    for feedback_path in sorted(Path("attempts").glob("*/feedback.md")):
        text = feedback_path.read_text()
        for line in text.splitlines():
            m = re.match(r"- (the artifact .+)$", line.strip())
            if not m or m.group(1) not in REQUIREMENT:
                continue
            name, description = REQUIREMENT[m.group(1)]
            proposals.append({
                "name": name,
                "description": description,
                "feasible": True,
                "task_level_rationale": "A property of any answer to this task, not of one attempt.",
                "applies_to_different_solution_strategies": True,
                "cited_source_id": feedback_path.as_posix(),
                "quote": m.group(1),
                "cited_evidence": f"{feedback_path.parent.name}: {m.group(1)}",
            })
            break
        if proposals:
            break
    print(json.dumps({"new_criteria": proposals, "notes": "scripted demo proposer"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
