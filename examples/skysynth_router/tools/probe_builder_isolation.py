#!/usr/bin/env python3
"""Verify that a BUILDER process under this config's sandbox cannot read the private data.

    python tools/probe_builder_isolation.py --config configs/static/task.yaml

Builds the exact srt settings CORAL would build for an agent of this config
(same function, ``coral.sandbox.srt.build_srt_settings``, against a throwaway
run layout), then runs a shell under srt and tries to read the private data
root, the run's ``.coral/private``, and ``~/.ssh``. Any READABLE is a failure
and the exit code is non-zero. It also confirms one path that must be
readable (``/etc/hosts``) so a broken sandbox that denies everything does not
pass by accident.

The candidate-policy sandbox is a separate, tighter boundary; this probe is
about the coding agents, which otherwise run as the user and could read
anything the user can.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument(
        "--private-root",
        type=Path,
        default=os.environ.get("SKYSYNTH_PRIVATE"),
        help="owner-only data root (default: $SKYSYNTH_PRIVATE); must be unreadable under the sandbox",
    )
    args = ap.parse_args(argv)
    if not args.private_root:
        print("FAIL: --private-root or SKYSYNTH_PRIVATE is required")
        return 1
    from coral.config import SandboxConfig
    from coral.sandbox.srt import build_srt_settings

    cfg = yaml.safe_load(args.config.read_text())
    sb_raw = ((cfg.get("agents") or {}).get("sandbox")) or {}
    if not sb_raw.get("enabled"):
        print("FAIL: agents.sandbox.enabled is not true in", args.config)
        return 1
    sb = SandboxConfig(
        **{k: v for k, v in sb_raw.items() if k in SandboxConfig.__dataclass_fields__}
    )
    private_root = Path(args.private_root).resolve()

    with tempfile.TemporaryDirectory(prefix="isoprobe-") as d:
        run = Path(d) / "run"
        for sub in (".coral/public", ".coral/private", "repo", "agents/a1"):
            (run / sub).mkdir(parents=True)
        (run / ".coral" / "private" / "secret").write_text("x")
        # allowlist mode needs no proxy; network is irrelevant to this probe.
        probe_cfg = SandboxConfig(
            enabled=True,
            network="allowlist",
            srt_command=sb.srt_command,
            deny_read=list(sb.deny_read),
            allow_read=list(sb.allow_read),
            allow_write=list(sb.allow_write),
        )
        settings = build_srt_settings(
            probe_cfg,
            worktree_path=run / "agents" / "a1",
            coral_dir=run / ".coral",
            repo_dir=run / "repo",
            shared_dir_name=".claude",
            proxy_port=None,
        )
        sp = Path(d) / "settings.json"
        sp.write_text(json.dumps(settings))
        targets = {
            "private_root": next(private_root.rglob("*.json"), private_root),
            "run_private": run / ".coral" / "private" / "secret",
            "home_ssh": Path.home() / ".ssh",
        }
        results = {}
        for name, path in targets.items():
            cmd = [
                *sb.srt_command,
                "--settings",
                str(sp),
                "--",
                "/bin/bash",
                "-c",
                f"( [ -d '{path}' ] && ls '{path}' || head -c 8 '{path}' ) >/dev/null 2>&1 && echo READABLE || echo DENIED",
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            out = r.stdout.strip().splitlines()
            results[name] = out[-1] if out else f"ERROR {r.stderr.strip()[-200:]}"
        cmd = [
            *sb.srt_command,
            "--settings",
            str(sp),
            "--",
            "/bin/bash",
            "-c",
            "head -c 8 /etc/hosts >/dev/null 2>&1 && echo READABLE || echo DENIED",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        results["system_control"] = (r.stdout.strip().splitlines() or ["ERROR"])[-1]

    ok = (
        all(v == "DENIED" for k, v in results.items() if k != "system_control")
        and results["system_control"] == "READABLE"
    )
    for k, v in results.items():
        print(f"{k:16} {v}")
    print("builder isolation:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
