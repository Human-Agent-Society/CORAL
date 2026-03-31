"""ASGI middleware for intercepting and logging agent model traffic."""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache commit hashes briefly to avoid hammering git on every request
_HASH_CACHE_TTL = 2.0  # seconds


class CoralGatewayMiddleware:
    """ASGI middleware that wraps LiteLLM's app to intercept agent requests.

    For each request:
    1. Identifies the agent by its unique API key
    2. Reads the agent's current git commit hash (cached briefly)
    3. Adds X-Coral-Agent-Id and X-Coral-Session-Id headers
    4. Logs request and assembled response as linked JSONL entries
    """

    def __init__(self, app: Any, log_dir: Path, master_key: str) -> None:
        self.app = app
        self.log_dir = log_dir
        self.master_key = master_key
        self._agent_map: dict[str, AgentInfo] = {}  # proxy_key -> agent info
        self._hash_cache: dict[str, tuple[str, float]] = {}  # worktree -> (hash, timestamp)

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.log_dir / "requests.jsonl"

    def register_agent(self, agent_id: str, worktree_path: Path, proxy_key: str) -> None:
        """Register an agent with its proxy key for identification."""
        self._agent_map[proxy_key] = AgentInfo(
            agent_id=agent_id,
            worktree_path=worktree_path,
        )

    def _get_agent_info(self, auth_header: str) -> AgentInfo | None:
        """Look up agent info from the Authorization header.

        Falls back to the sole registered agent if the key doesn't match
        (e.g. when OpenCode uses a static apiKey from opencode.json).
        """
        if not auth_header:
            if len(self._agent_map) == 1:
                return next(iter(self._agent_map.values()))
            return None
        # Extract bearer token
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            if len(self._agent_map) == 1:
                return next(iter(self._agent_map.values()))
            return None
        token = parts[1]
        info = self._agent_map.get(token)
        if info:
            return info
        # Key not recognized — fall back to sole agent if only one registered
        if len(self._agent_map) == 1:
            return next(iter(self._agent_map.values()))
        return None

    def _get_commit_hash(self, worktree_path: Path) -> str:
        """Get the current commit hash for a worktree, with brief caching."""
        key = str(worktree_path)
        now = time.monotonic()

        cached = self._hash_cache.get(key)
        if cached and (now - cached[1]) < _HASH_CACHE_TTL:
            return cached[0]

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            commit_hash = result.stdout.strip()[:12] if result.returncode == 0 else "unknown"
        except Exception:
            commit_hash = "unknown"

        self._hash_cache[key] = (commit_hash, now)
        return commit_hash

    def _log_entry(self, entry: dict[str, Any]) -> None:
        """Append a JSONL entry to the log file."""
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write gateway log: {e}")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> Any:
        """ASGI interface — intercept HTTP requests."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Extract request info from ASGI scope
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Only intercept API calls, pass through health checks etc.
        if not _is_api_path(path):
            return await self.app(scope, receive, send)

        # Generate a unique request ID to link request and response
        request_id = str(uuid.uuid4())[:8]

        # Read headers — check both Authorization (OpenAI) and x-api-key (Anthropic)
        auth_header = ""
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower() if isinstance(raw_name, bytes) else raw_name.lower()
            if name == "authorization":
                auth_header = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else raw_value
                break
            elif name == "x-api-key" and not auth_header:
                val = raw_value.decode("latin-1") if isinstance(raw_value, bytes) else raw_value
                auth_header = f"Bearer {val}"

        # Identify agent
        agent_info = self._get_agent_info(auth_header)
        agent_id = agent_info.agent_id if agent_info else "unknown"
        session_id = "unknown"
        if agent_info:
            session_id = self._get_commit_hash(agent_info.worktree_path)

        # Read request body
        body_parts: list[bytes] = []

        async def receive_wrapper() -> dict:
            message = await receive()
            if message.get("type") == "http.request":
                body_parts.append(message.get("body", b""))
            return message

        # Add CORAL headers to the request and replace auth with master key
        new_headers = []
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower() if isinstance(raw_name, bytes) else raw_name.lower()
            if name == "authorization" and self.master_key:
                # Replace agent's proxy key with the LiteLLM master key
                new_headers.append((raw_name, f"Bearer {self.master_key}".encode("latin-1")))
            else:
                new_headers.append((raw_name, raw_value))

        # Add CORAL-specific headers
        new_headers.append((b"x-coral-agent-id", agent_id.encode("latin-1")))
        new_headers.append((b"x-coral-session-id", session_id.encode("latin-1")))
        scope["headers"] = new_headers

        # Track response
        start_time = time.monotonic()
        response_status = 0
        response_body_parts: list[bytes] = []

        async def send_wrapper(message: dict) -> None:
            nonlocal response_status
            if message.get("type") == "http.response.start":
                response_status = message.get("status", 0)
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if body:
                    response_body_parts.append(body)
            await send(message)

        # Pass through to LiteLLM
        await self.app(scope, receive_wrapper, send_wrapper)

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Log request (with messages trimmed for readability)
        request_body = b"".join(body_parts)
        request_body_parsed = _safe_parse_json(request_body)
        request_model = None
        if isinstance(request_body_parsed, dict):
            request_model = request_body_parsed.get("model")

        self._log_entry({
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "session_id": session_id,
            "method": method,
            "path": path,
            "model": request_model,
            "request": request_body_parsed,
            "response": _assemble_response(b"".join(response_body_parts)),
            "status_code": response_status,
            "duration_ms": duration_ms,
        })

        return None


class AgentInfo:
    """Metadata about a registered agent."""

    __slots__ = ("agent_id", "worktree_path")

    def __init__(self, agent_id: str, worktree_path: Path) -> None:
        self.agent_id = agent_id
        self.worktree_path = worktree_path


def _is_api_path(path: str) -> bool:
    """Check if a path is an API endpoint worth intercepting."""
    api_prefixes = (
        "/v1/messages",
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/completions",
        "/completions",
    )
    return any(path.startswith(p) for p in api_prefixes)


def _assemble_response(data: bytes) -> Any:
    """Assemble a response body into a clean structure.

    For streaming SSE responses, concatenates the text content from all chunks
    into a single assembled message. For non-streaming responses, parses as JSON.
    """
    if not data:
        return None

    raw = data.decode("utf-8", errors="replace")

    # Check if this is an SSE stream (starts with "data: ")
    if not raw.lstrip().startswith("data:"):
        return _safe_parse_json(data)

    # Parse SSE chunks and assemble content
    content_parts: list[str] = []
    model = None
    finish_reason = None
    usage = None
    response_id = None

    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            continue

        if not response_id and chunk.get("id"):
            response_id = chunk["id"]
        if not model and chunk.get("model"):
            model = chunk["model"]

        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})
            text = delta.get("content", "")
            if text:
                content_parts.append(text)
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

        if chunk.get("usage"):
            usage = chunk["usage"]

    assembled: dict[str, Any] = {}
    if response_id:
        assembled["id"] = response_id
    if model:
        assembled["model"] = model
    if content_parts:
        assembled["content"] = "".join(content_parts)
    if finish_reason:
        assembled["finish_reason"] = finish_reason
    if usage:
        assembled["usage"] = usage

    return assembled


def _safe_parse_json(data: bytes) -> Any:
    """Try to parse bytes as JSON, fall back to string."""
    if not data:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return "<binary>"
