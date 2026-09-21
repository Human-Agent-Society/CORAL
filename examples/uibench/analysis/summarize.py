"""Tables for the case-study write-up, from ledger.json and seed_trajectories.json.

Four tables, each a different question:

1. **Outcome after receipt** -- for every evolved criterion, each agent's score
   at first receipt and at its last scored attempt. Shown per agent, not
   averaged, because four agents is four numbers and a mean of four hides
   which ones moved.
2. **Seed criteria by arm** -- for all six runs, each seed criterion's mean over
   the first two scored attempts per agent versus the last two. The static arm
   sits beside the evolving ones as the plan's descriptive comparison. No
   inference is drawn from it; it is what the static arm did.
3. **Receipt** -- for every evolved criterion, the first scored attempt under it
   by any agent, each agent's own first, the lag between them, and any public
   note that named it with its mtime.
4. **Checkpoints** -- every checkpoint outcome, including the voided one.

Nothing here is a test. These are the numbers, arranged so the reader can see
them.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from intervention_identity import arm_label, has_replicates  # noqa: E402

AGENTS = ("captain-ahab", "captain-nemo", "davy-jones", "jack-sparrow")
SHORT = {
    "captain-ahab": "ahab",
    "captain-nemo": "nemo",
    "davy-jones": "davy",
    "jack-sparrow": "jack",
}
SEED = (
    "Build Smoothness",
    "Implementation Quality",
    "Instruction Following",
    "Visual Quality",
    "Interaction Experience",
)


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _f(x):
    return "–" if x is None else f"{x:.2f}"


def outcome_table(ledger: list[dict]) -> str:
    replicates = has_replicates(ledger)
    rows = [
        "| task | arm | v | criterion | "
        + " | ".join(f"{SHORT[a]} first→last" for a in AGENTS)
        + " | n later |",
        "|---|---|---|---|" + "---|" * len(AGENTS) + "---|",
    ]
    for r in ledger:
        cells = []
        for a in AGENTS:
            pa = r["per_agent"][a]
            fl = pa.get("score_first_to_last")
            n = pa["n_subsequent_scored"]
            if not fl:
                cells.append("–")
            elif n == 1:
                cells.append(f"{fl[0]:.2f} (1 only)")
            else:
                d = fl[1] - fl[0]
                cells.append(f"{fl[0]:.2f}→{fl[1]:.2f} ({d:+.2f})")
        later = sum(r["per_agent"][a]["n_subsequent_scored"] for a in AGENTS)
        rows.append(
            f"| {r['task']} | {arm_label(r, replicates)} | {r['version']} | {r['name']} | "
            + " | ".join(cells)
            + f" | {later} |"
        )
    return "\n".join(rows)


def seed_table(seeds: dict) -> str:
    rows = [
        "| task | arm | " + " | ".join(s.split()[0] for s in SEED) + " |",
        "|---|---|" + "---|" * len(SEED),
    ]
    for run, per_agent in seeds.items():
        task, arm = run.split("_")
        cells = []
        for s in SEED:
            firsts, lasts = [], []
            for a in AGENTS:
                tr = [x["score"] for x in per_agent.get(a, {}).get(s, [])]
                if len(tr) >= 2:
                    firsts.extend(tr[:2])
                    lasts.extend(tr[-2:])
                elif tr:
                    firsts.append(tr[0])
                    lasts.append(tr[-1])
            if firsts:
                cells.append(
                    f"{st.mean(firsts):.2f}→{st.mean(lasts):.2f} ({st.mean(lasts) - st.mean(firsts):+.2f})"
                )
            else:
                cells.append("–")
        rows.append(f"| {task} | {arm} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def receipt_table(ledger: list[dict]) -> str:
    replicates = has_replicates(ledger)
    rows = [
        "| task | arm | v | criterion | published | first scored under it (any agent) | own-receipt lag per agent (min) | notes naming it (mtime) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in ledger:
        pub = _dt(r["published_at"])
        fa = r.get("first_receipt_any_agent") or {}
        fa_t = _dt(fa.get("written_at"))
        lags = []
        for a in AGENTS:
            fr = r["per_agent"][a].get("first_own_receipt")
            if fr and fa_t:
                lags.append(f"{SHORT[a]} {(_dt(fr['written_at']) - fa_t).total_seconds() / 60:.0f}")
            else:
                lags.append(f"{SHORT[a]} –")
        notes = (
            "; ".join(
                f"{n['file'][:28]} @{(n.get('mtime') or '')[11:16]}"
                for n in r.get("public_notes_naming_it", [])
            )
            or "–"
        )
        pub_to_first = f"+{(fa_t - pub).total_seconds() / 60:.0f} min" if (pub and fa_t) else "–"
        rows.append(
            f"| {r['task']} | {arm_label(r, replicates)} | {r['version']} | {r['name']} | {r['published_at'][11:16] if r['published_at'] else '–'} | "
            f"{(fa.get('agent') or '–')} {pub_to_first} | {', '.join(lags)} | {notes} |"
        )
    return "\n".join(rows)


def checkpoint_table(checkpoints: list[dict]) -> str:
    rows = [
        "| task | arm | after | status | proposed | published | replay |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in checkpoints:
        for cp in run["checkpoints"]:
            d = cp.get("detail", {})
            replay = ""
            if run["arm"] == "yoked":
                want = d.get("required_count")
                got = d.get("accepted_count")
                replay = f"needed {want}, got {got}" + (
                    " — **void**" if want is not None and got is not None and want != got else " ✓"
                )
            rows.append(
                f"| {run['task']} | {run['arm']} | {cp['finalized_attempts']} | {cp['status']} | "
                f"{len(cp.get('proposed', []))} | {len(cp.get('published', []))} | {replay} |"
            )
    return "\n".join(rows)


def main() -> int:
    ledger = json.loads((HERE / "ledger.json").read_text())
    seeds = json.loads((HERE / "seed_trajectories.json").read_text())
    cps = json.loads((HERE / "checkpoints.json").read_text())
    out = [
        "# Summary tables",
        "",
        "Generated by `summarize.py` from `ledger.json`, `seed_trajectories.json` and `checkpoints.json`. "
        "Per-agent, not averaged: four agents is four numbers.",
        "",
        "**Timing correction:** legacy `receipt` labels denote feedback-writing events, not verified "
        "reading or exposure bounds. Counts are availability-based sensitivity scenarios. "
        "Peer notes substantiate the specific propagation events they describe, not universal receipt.",
        "",
        "## 1. Evolved criteria: first scored feedback → last scored attempt",
        "",
        "A criterion published late leaves each agent one or two scored attempts; those rows say `(1 only)`. "
        "A rise after receipt is consistent with response and with regression to the mean and with the "
        "evaluator's own noise, none of which this table separates.",
        "",
        outcome_table(ledger),
        "",
        "## 2. Seed criteria, all six runs: mean of first two scored attempts per agent → last two",
        "",
        "The static arm's rows are the descriptive comparison. The evolving arms' seed scores were produced "
        "under rubrics that grew during the run, so a change here can be the artifacts changing or the "
        "evaluator's attention being redistributed across more criteria.",
        "",
        seed_table(seeds),
        "",
        "## 3. Feedback availability: two timing scenarios, not actual receipt",
        "",
        "`published` is the rubric version's creation time (UTC, HH:MM). `first scored under it` is the earliest "
        "scoring event carrying the criterion, by any agent, and how long after publication it came — from that "
        "moment the criterion's text was in a public attempt file. `own-receipt lag` is each agent's own first "
        "scored attempt under it, minutes after that. Notes are agent-authored and timed by mtime.",
        "",
        receipt_table(ledger),
        "",
        "## 4. Checkpoints",
        "",
        checkpoint_table(cps),
        "",
    ]
    (HERE / "summary_tables.md").write_text("\n".join(out))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
