"""Write the registered topology-invariant N=512 initial candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path

N = 512
SALT = "coral-threshold-v4"


def base_agent_id(agent_id: str) -> str:
    return agent_id.strip().split("-from-", 1)[0]


def initial_candidate(agent_id: str) -> str:
    digest = hashlib.sha256(f"{SALT}:{base_agent_id(agent_id)}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < N:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:N]


def main() -> None:
    root = Path(__file__).resolve().parent
    agent_file = root / ".coral_agent_id"
    if not agent_file.is_file():
        raise SystemExit("missing .coral_agent_id; run this inside a CORAL agent worktree")
    agent_id = agent_file.read_text()
    candidate = initial_candidate(agent_id)
    (root / "candidate.py").write_text(
        '\"\"\"Registered topology-invariant N=512 initial candidate.\"\"\"\n\n'
        f'CANDIDATE = "{candidate}"\n'
    )
    print(f"wrote {len(candidate)} bits for {base_agent_id(agent_id)}")


if __name__ == "__main__":
    main()
