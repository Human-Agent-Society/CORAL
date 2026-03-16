"""Parse Claude Code NDJSON logs into structured turns for the web UI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LogEntry:
    """A single meaningful event extracted from a log."""

    # Types: thinking, tool_call, tool_result, text, system, error,
    #        coral_prompt, subagent_start, subagent_progress, subagent_done,
    #        compact, result
    type: str
    content: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    turn_index: int = 0


@dataclass
class LogTurn:
    """A conversation turn (assistant message + tool results)."""

    index: int
    entries: list[LogEntry] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "entries": [
                {
                    "type": e.type,
                    "content": e.content,
                    "details": e.details,
                    "timestamp": e.timestamp,
                }
                for e in self.entries
            ],
            "usage": self.usage,
            "timestamp": self.timestamp,
        }


def _truncate(text: str, max_lines: int = 25) -> str:
    """Truncate text to max_lines, keeping first and last portions."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    head = lines[: max_lines - 5]
    tail = lines[-3:]
    return "\n".join(head + [f"\n... ({len(lines) - max_lines + 2} lines omitted) ...\n"] + tail)


def _extract_content_blocks(content_list: list[dict]) -> list[LogEntry]:
    """Extract structured entries from an assistant message's content array."""
    entries = []
    for block in content_list:
        block_type = block.get("type", "")

        if block_type == "thinking":
            text = block.get("thinking", "")
            if text:
                entries.append(LogEntry(
                    type="thinking",
                    content=_truncate(text, max_lines=50),
                ))

        elif block_type == "text":
            text = block.get("text", "")
            if text:
                entries.append(LogEntry(type="text", content=text))

        elif block_type == "tool_use":
            name = block.get("name", "unknown")
            tool_input = block.get("input", {})
            # Summarize tool input
            summary = _summarize_tool_input(name, tool_input)
            entries.append(LogEntry(
                type="tool_call",
                content=name,
                details={"input_summary": summary, "tool_use_id": block.get("id", "")},
            ))

        elif block_type == "tool_result":
            content = block.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            entries.append(LogEntry(
                type="tool_result",
                content=_truncate(str(content)),
                details={"tool_use_id": block.get("tool_use_id", "")},
            ))

    return entries


def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a short summary of tool input."""
    if not isinstance(tool_input, dict):
        return str(tool_input)[:200]

    if tool_name in ("Read", "read_file"):
        return tool_input.get("file_path", tool_input.get("path", ""))
    elif tool_name in ("Edit", "edit_file"):
        return tool_input.get("file_path", tool_input.get("path", ""))
    elif tool_name in ("Write", "write_file"):
        return tool_input.get("file_path", tool_input.get("path", ""))
    elif tool_name in ("Bash", "bash"):
        cmd = tool_input.get("command", "")
        return cmd[:200] if cmd else ""
    elif tool_name in ("Grep", "grep"):
        return f"/{tool_input.get('pattern', '')}/ in {tool_input.get('path', '.')}"
    elif tool_name in ("Glob", "glob"):
        return tool_input.get("pattern", "")
    elif tool_name == "Agent":
        return tool_input.get("description", tool_input.get("prompt", ""))[:200]
    else:
        # Generic: show first key-value
        for k, v in tool_input.items():
            return f"{k}: {str(v)[:150]}"
    return ""


@dataclass
class SessionMeta:
    """Metadata from the result message at the end of a session."""

    total_cost_usd: float | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    stop_reason: str = ""
    session_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    model_usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "duration_ms": self.duration_ms,
            "duration_api_ms": self.duration_api_ms,
            "num_turns": self.num_turns,
            "stop_reason": self.stop_reason,
            "session_id": self.session_id,
            "usage": self.usage,
            "model_usage": self.model_usage,
        }


def parse_log_file(
    path: Path, offset: int = 0
) -> tuple[list[LogTurn], int, SessionMeta | None]:
    """Parse a Claude Code NDJSON log file into structured turns.

    Args:
        path: Path to the log file.
        offset: Byte offset to start reading from (for incremental updates).

    Returns:
        (list of LogTurn, new byte offset, session metadata from result message)
    """
    if not path.exists():
        return [], 0, None

    file_size = path.stat().st_size
    if offset >= file_size:
        return [], offset, None

    turns: list[LogTurn] = []
    current_turn: LogTurn | None = None
    turn_index = 0
    session_meta: SessionMeta | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        if offset > 0:
            f.seek(offset)

        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type", "")

            if msg_type == "coral":
                # CORAL prompt injection (initial instruction, heartbeat, restart)
                subtype = obj.get("subtype", "")
                if subtype == "prompt":
                    source = obj.get("source", "")
                    prompt_text = obj.get("prompt", "")
                    timestamp = obj.get("timestamp", "")
                    details: dict[str, Any] = {"source": source}
                    task_name = obj.get("task_name")
                    task_description = obj.get("task_description")
                    if task_name:
                        details["task_name"] = task_name
                    if task_description:
                        details["task_description"] = task_description
                    # For start/restart, show task description instead of bare "Begin."
                    if source in ("start", "restart") and task_description:
                        display_content = task_description
                    else:
                        display_content = prompt_text
                    entry = LogEntry(
                        type="coral_prompt",
                        content=display_content,
                        details=details,
                        timestamp=timestamp,
                    )
                    # Start a new turn for the coral prompt
                    if current_turn and current_turn.entries:
                        turns.append(current_turn)
                    current_turn = LogTurn(index=turn_index, timestamp=timestamp)
                    turn_index += 1
                    current_turn.entries.append(entry)
                continue

            if msg_type == "system":
                subtype = obj.get("subtype", "")

                if subtype == "init":
                    model = obj.get("model", "")
                    session_id = obj.get("session_id", "")
                    entry = LogEntry(
                        type="system",
                        content=f"Session started (model: {model})",
                        details={
                            "session_id": session_id,
                            "model": model,
                            "tools": obj.get("tools", []),
                            "skills": obj.get("skills", []),
                            "agents": obj.get("agents", []),
                            "plugins": [
                                p.get("name", "") if isinstance(p, dict) else str(p)
                                for p in obj.get("plugins", [])
                            ],
                            "claude_code_version": obj.get("claude_code_version", ""),
                        },
                    )
                    if current_turn is None:
                        current_turn = LogTurn(index=turn_index)
                        turn_index += 1
                    current_turn.entries.append(entry)

                elif subtype == "task_started":
                    # Subagent launched
                    entry = LogEntry(
                        type="subagent_start",
                        content=obj.get("description", ""),
                        details={
                            "task_id": obj.get("task_id", ""),
                            "prompt": _truncate(obj.get("prompt", ""), max_lines=10),
                            "task_type": obj.get("task_type", ""),
                        },
                    )
                    if current_turn is None:
                        current_turn = LogTurn(index=turn_index)
                        turn_index += 1
                    current_turn.entries.append(entry)

                elif subtype == "task_progress":
                    # Subagent progress — tool calls etc.
                    task_usage = obj.get("usage", {})
                    entry = LogEntry(
                        type="subagent_progress",
                        content=obj.get("last_tool_name", ""),
                        details={
                            "task_id": obj.get("task_id", ""),
                            "description": obj.get("description", ""),
                            "tool_uses": task_usage.get("tool_uses", 0),
                        },
                    )
                    if current_turn is None:
                        current_turn = LogTurn(index=turn_index)
                        turn_index += 1
                    current_turn.entries.append(entry)

                elif subtype == "task_notification":
                    # Subagent completed
                    task_usage = obj.get("usage", {})
                    entry = LogEntry(
                        type="subagent_done",
                        content=obj.get("summary", ""),
                        details={
                            "task_id": obj.get("task_id", ""),
                            "status": obj.get("status", ""),
                            "total_tokens": task_usage.get("total_tokens", 0),
                            "tool_uses": task_usage.get("tool_uses", 0),
                            "duration_ms": task_usage.get("duration_ms", 0),
                        },
                    )
                    if current_turn is None:
                        current_turn = LogTurn(index=turn_index)
                        turn_index += 1
                    current_turn.entries.append(entry)

                elif subtype == "compact_boundary":
                    # Context compaction boundary
                    meta = obj.get("compact_metadata", {})
                    entry = LogEntry(
                        type="compact",
                        content=f"Context compacted ({meta.get('trigger', 'auto')})",
                        details={"pre_tokens": meta.get("pre_tokens", 0)},
                    )
                    if current_turn and current_turn.entries:
                        turns.append(current_turn)
                    current_turn = LogTurn(index=turn_index)
                    turn_index += 1
                    current_turn.entries.append(entry)

                # system:status silently ignored (just "compacting" state changes)

            elif msg_type == "assistant":
                message = obj.get("message", {})
                content = message.get("content", [])
                usage = message.get("usage", {})

                parsed_usage = {}
                if usage:
                    parsed_usage = {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_creation": usage.get("cache_creation_input_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                    }

                # Same usage as current turn = same API response logged as
                # multiple NDJSON lines (one per content block). Merge them.
                if current_turn and current_turn.usage and parsed_usage == current_turn.usage:
                    if isinstance(content, list):
                        current_turn.entries.extend(_extract_content_blocks(content))
                else:
                    # New API call — start a new turn
                    if current_turn and current_turn.entries:
                        turns.append(current_turn)
                    current_turn = LogTurn(index=turn_index)
                    turn_index += 1
                    if isinstance(content, list):
                        current_turn.entries.extend(_extract_content_blocks(content))
                    if parsed_usage:
                        current_turn.usage = parsed_usage

            elif msg_type == "user":
                # Tool results come as user messages
                message = obj.get("message", {})
                content = message.get("content", [])
                if isinstance(content, list):
                    entries = _extract_content_blocks(content)
                    if current_turn:
                        current_turn.entries.extend(entries)

            elif msg_type == "result":
                # Final result — extract full metadata
                result_text = obj.get("result", "")
                result_usage = obj.get("usage", {})
                model_usage = obj.get("modelUsage", {})
                session_meta = SessionMeta(
                    total_cost_usd=obj.get("total_cost_usd"),
                    duration_ms=obj.get("duration_ms"),
                    duration_api_ms=obj.get("duration_api_ms"),
                    num_turns=obj.get("num_turns"),
                    stop_reason=obj.get("stop_reason", ""),
                    session_id=obj.get("session_id", ""),
                    usage=result_usage,
                    model_usage=model_usage,
                )
                # Add result entry to current turn
                entry = LogEntry(
                    type="result",
                    content=str(result_text)[:500] if result_text else "",
                    details={
                        "total_cost_usd": obj.get("total_cost_usd"),
                        "duration_ms": obj.get("duration_ms"),
                        "num_turns": obj.get("num_turns"),
                        "stop_reason": obj.get("stop_reason", ""),
                    },
                )
                if current_turn is None:
                    current_turn = LogTurn(index=turn_index)
                    turn_index += 1
                current_turn.entries.append(entry)

    # Append the last turn
    if current_turn and current_turn.entries:
        turns.append(current_turn)

    new_offset = path.stat().st_size
    return turns, new_offset, session_meta


def list_log_files(coral_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """List all log files grouped by agent ID.

    Returns:
        {agent_id: [{path, index, size_bytes, modified}]}
    """
    logs_dir = coral_dir / "public" / "logs"
    if not logs_dir.exists():
        return {}

    agents: dict[str, list[dict[str, Any]]] = {}
    for log_file in sorted(logs_dir.glob("*.log")):
        parts = log_file.stem.rsplit(".", 1)
        agent_id = parts[0] if len(parts) == 2 else log_file.stem
        index = int(parts[1]) if len(parts) == 2 else 0
        stat = log_file.stat()
        agents.setdefault(agent_id, []).append({
            "path": str(log_file),
            "index": index,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })

    return agents
