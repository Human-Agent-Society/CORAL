"""Local interactive chat module (design/chat-module.md).

P1: a stream-json bridge to a local `claude` session. Later phases add
workspace gating (P2), a `coral start` approval hook (P3), and transcript
persistence + UI (P4).
"""

from __future__ import annotations

from coral.chat.session import ChatSession, ChatSessionManager

__all__ = ["ChatSession", "ChatSessionManager"]
