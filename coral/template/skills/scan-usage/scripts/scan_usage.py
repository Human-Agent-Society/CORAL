#!/usr/bin/env python3
"""scan_usage.py — Measure which shared notes and skills agents actually read.

Scans agent session logs (NDJSON) for agent-initiated tool calls that touch
the shared notes/ and skills/ directories, then cross-references the files
that exist on disk. This gives the librarian *outcome evidence* — which
knowledge is actually consumed — instead of relying on agents to self-report.

Usage:
    python scan_usage.py [LOGS_DIR] [--notes-dir DIR] [--skills-dir DIR]
                         [--agent ID] [--top N] [--json]

Defaults assume it runs inside an agent worktree: logs at .claude/logs,
notes at .claude/notes, skills at .claude/skills (any shared_dir name works —
.codex/.opencode/... paths in logs are matched too).

What counts:
  - note READ: Read tool on notes/<path>.md, or a Bash command that names a
    specific note file (cat/sed/grep/head/...).
  - note WRITE: Write/Edit/NotebookEdit on notes/<path>.md.
  - note BROWSE: Glob/Grep patterns under notes/ (discovery, not consumption).
  - skill USE: Skill tool invocation, Read of any file inside skills/<name>/,
    or a Bash command referencing skills/<name>/ (e.g. running its scripts),
    or `coral skills --read <name>`.

Only assistant-initiated tool calls are counted — tool *results* (directory
listings, note contents echoing other paths) are ignored, so `ls notes/`
does not mark every note as read.

This script NEVER modifies any files. Self-contained — no coral imports.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# <dot-dir>/notes/<relpath with extension>  e.g. .claude/notes/experiments/foo.md
# also matches .coral/public/notes/... and .coral/islands/3/notes/...
_NOTE_RE = re.compile(
    r"(?:\.[A-Za-z][\w.-]*|public|islands/\d+)/notes/((?:[\w.+-]+/)*[\w.+-]+\.\w+)"
)
_SKILL_RE = re.compile(r"(?:\.[A-Za-z][\w.-]*|public|islands/\d+)/skills/([\w-]+)")
_CORAL_SKILLS_READ_RE = re.compile(r"coral\s+skills\s+--read[\s=]+([\w-]+)")
# `... > notes/x.md`, `... >> notes/x.md`, `... | tee notes/x.md` are writes;
# trailing [\w./-]* absorbs an absolute-path prefix before the matched dot-dir
_SHELL_REDIRECT_RE = re.compile(r"(?:>>?|\btee(?:\s+-a)?)\s*['\"]?[\w./-]*$")

_READ_TOOLS = {"Read"}
_WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}
_BROWSE_TOOLS = {"Glob", "Grep"}


def _agent_id_from_log(path: Path) -> str:
    """agent-1.3.log -> agent-1 (logs are named <agent_id>.<index>.log)."""
    parts = path.stem.rsplit(".", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else path.stem


def _iter_tool_uses(path: Path):
    """Yield (tool_name, input_dict) for agent-initiated tool calls in a log.

    Supports Claude Code stream-json (assistant messages with tool_use
    blocks). Other runtimes' JSONL is handled tolerantly: any event carrying
    a top-level or item-level "command" string (Codex-style command
    execution) is yielded as a Bash call. Unknown lines are skipped.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue

            msg_type = obj.get("type", "")
            if msg_type == "assistant":
                content = obj.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            yield block.get("name", ""), block.get("input") or {}
            elif msg_type in ("user", "result", "system", "coral"):
                # Tool results / metadata — never count paths echoed in output.
                continue
            else:
                # Non-Claude-Code runtimes: pick up command-execution events.
                cmd = obj.get("command")
                if cmd is None and isinstance(obj.get("item"), dict):
                    cmd = obj["item"].get("command")
                if isinstance(cmd, list):
                    cmd = " ".join(str(c) for c in cmd)
                if isinstance(cmd, str) and cmd:
                    yield "Bash", {"command": cmd}


def _new_stats() -> dict:
    return {
        "reads": 0,
        "writes": 0,
        "browses": 0,
        "readers": defaultdict(int),
        "writers": defaultdict(int),
    }


def scan_logs(logs_dir: Path, only_agent: str | None = None) -> tuple[dict, dict, int]:
    """Return (note_stats, skill_stats, unresolved_note_reads).

    note_stats:  {relpath: {reads, writes, browses, readers{agent: n}, writers{agent: n}}}
    skill_stats: {name:    {uses, users{agent: n}}}
    unresolved_note_reads counts `coral notes --read N` calls (index-based,
    can't be mapped back to a filename after the fact).
    """
    notes: dict[str, dict] = defaultdict(_new_stats)
    skills: dict[str, dict] = defaultdict(lambda: {"uses": 0, "users": defaultdict(int)})
    unresolved = 0

    for log_file in sorted(logs_dir.glob("*.log")):
        agent = _agent_id_from_log(log_file)
        if only_agent and agent != only_agent:
            continue
        for tool, tool_input in _iter_tool_uses(log_file):
            if not isinstance(tool_input, dict):
                continue

            if tool == "Skill":
                name = tool_input.get("skill") or tool_input.get("name") or ""
                # Strip plugin namespacing like "coral:deep-research".
                name = str(name).rsplit(":", 1)[-1]
                if name:
                    skills[name]["uses"] += 1
                    skills[name]["users"][agent] += 1
                continue

            if tool in _READ_TOOLS or tool in _WRITE_TOOLS:
                text = str(tool_input.get("file_path") or tool_input.get("path") or "")
                kind = "read" if tool in _READ_TOOLS else "write"
            elif tool in _BROWSE_TOOLS:
                text = f"{tool_input.get('path') or ''} {tool_input.get('pattern') or ''}"
                kind = "browse"
            elif tool == "Bash":
                text = str(tool_input.get("command") or "")
                kind = "read"  # naming a specific file in a command ≈ consuming it
                if re.search(r"coral\s+notes\s+--read\b", text):
                    unresolved += 1
                for m in _CORAL_SKILLS_READ_RE.finditer(text):
                    skills[m.group(1)]["uses"] += 1
                    skills[m.group(1)]["users"][agent] += 1
            else:
                continue

            for m in _NOTE_RE.finditer(text):
                rel = m.group(1)
                stats = notes[rel]
                hit_kind = kind
                if tool == "Bash" and _SHELL_REDIRECT_RE.search(text[: m.start()]):
                    hit_kind = "write"
                if hit_kind == "read":
                    stats["reads"] += 1
                    stats["readers"][agent] += 1
                elif hit_kind == "write":
                    stats["writes"] += 1
                    stats["writers"][agent] += 1
                else:
                    stats["browses"] += 1
            for m in _SKILL_RE.finditer(text):
                # Only consumption counts as a use — not browsing, not
                # authoring (Write/Edit or shell redirects into skills/).
                if kind != "read":
                    continue
                if tool == "Bash" and _SHELL_REDIRECT_RE.search(text[: m.start()]):
                    continue
                skills[m.group(1)]["uses"] += 1
                skills[m.group(1)]["users"][agent] += 1

    return dict(notes), dict(skills), unresolved


def inventory(notes_dir: Path, skills_dir: Path) -> tuple[list[str], list[str]]:
    """Files that exist on disk: (note relpaths, skill names)."""
    note_files = []
    if notes_dir.is_dir():
        note_files = sorted(
            str(p.relative_to(notes_dir))
            for p in notes_dir.rglob("*.md")
            if "_archive" not in p.relative_to(notes_dir).parts
        )
    skill_names = []
    if skills_dir.is_dir():
        skill_names = sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md"))
    return note_files, skill_names


def _fmt_agents(counts: dict) -> str:
    return ", ".join(f"{a}({n})" for a, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def render_text(report: dict, top: int) -> str:
    out = []
    sk = report["skills"]
    out.append(f"== Skills ({len(sk['on_disk'])} on disk) ==")
    ranked = sorted(sk["usage"].items(), key=lambda kv: -kv[1]["uses"])[:top]
    if ranked:
        width = max(len(name) for name, _ in ranked)
        for name, s in ranked:
            out.append(
                f"  {name:<{width}}  uses={s['uses']:<4} agents={len(s['users'])}  {_fmt_agents(s['users'])}"
            )
    if sk["never_used"]:
        out.append(f"  never used ({len(sk['never_used'])}): {', '.join(sk['never_used'])}")

    nt = report["notes"]
    out.append("")
    out.append(f"== Notes ({len(nt['on_disk'])} on disk) ==")
    ranked = sorted(nt["usage"].items(), key=lambda kv: -kv[1]["reads"])[:top]
    if ranked:
        width = max(len(p) for p, _ in ranked)
        for path, s in ranked:
            out.append(
                f"  {path:<{width}}  reads={s['reads']:<4} writes={s['writes']:<3} "
                f"distinct readers={len(s['readers'])}  {_fmt_agents(s['readers'])}"
            )
    if nt["never_read"]:
        out.append(f"  never read ({len(nt['never_read'])}):")
        for p in nt["never_read"]:
            out.append(f"    {p}")
    if nt["unresolved_reads"]:
        out.append(
            f"  (+{nt['unresolved_reads']} `coral notes --read N` calls that "
            f"can't be attributed to a specific note)"
        )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("logs_dir", nargs="?", default=".claude/logs", help="agent logs dir")
    parser.add_argument("--notes-dir", default=".claude/notes")
    parser.add_argument("--skills-dir", default=".claude/skills")
    parser.add_argument("--agent", help="only count one agent's activity")
    parser.add_argument("--top", type=int, default=30, help="max rows per table")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_dir():
        print(f"error: logs dir not found: {logs_dir}", file=sys.stderr)
        return 1

    note_usage, skill_usage, unresolved = scan_logs(logs_dir, args.agent)
    notes_on_disk, skills_on_disk = inventory(Path(args.notes_dir), Path(args.skills_dir))

    read_notes = {p for p, s in note_usage.items() if s["reads"] or s["browses"]}
    report = {
        "notes": {
            "on_disk": notes_on_disk,
            "usage": {
                p: {
                    "reads": s["reads"],
                    "writes": s["writes"],
                    "browses": s["browses"],
                    "readers": dict(s["readers"]),
                    "writers": dict(s["writers"]),
                }
                for p, s in note_usage.items()
            },
            "never_read": [p for p in notes_on_disk if p not in read_notes],
            "unresolved_reads": unresolved,
        },
        "skills": {
            "on_disk": skills_on_disk,
            "usage": {
                n: {"uses": s["uses"], "users": dict(s["users"])} for n, s in skill_usage.items()
            },
            "never_used": [n for n in skills_on_disk if n not in skill_usage],
        },
    }

    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
