"""Extract three retrospectively selected mechanism chains; no model calls.

Optional browser probes are case-specific reproductions, not a general oracle.
All original run artifacts and extracted records remain unchanged.
"""

import argparse
import functools
import http.server
import json
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
# examples/uibench/analysis -> repository root
REPO = HERE.parents[3]
NAMES = {
    "Simulated State Durability",
    "Simulated Dependency Traversability",
    "Keyboard Operability of the Interaction Model",
}


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True)


class _Served:
    """A directory on an ephemeral localhost port: a fresh origin per page, so no
    localStorage carries between probes."""

    def __init__(self, directory: Path):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def shutdown(self):
        self._server.shutdown()
        self._server.server_close()


def _serve(directory: Path) -> _Served:
    return _Served(directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    parser.add_argument(
        "--results",
        type=Path,
        default=REPO / "results",
        help="directory the runs of record live under (run_dir in raw/*.json is relative to it)",
    )
    parser.add_argument("--out", type=Path, default=HERE / "out" / "distinctive_response_audit")
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    ledger = json.loads((HERE / "ledger.json").read_text())
    chains = []
    for criterion in ledger:
        if criterion["name"] not in NAMES:
            continue
        raw = json.loads((HERE / "raw" / f"{criterion['task']}_adaptive.json").read_text())
        agents = []
        for agent, entry in criterion["per_agent"].items():
            own = entry["first_own_receipt"]
            source = args.results / raw["run_dir"] / "agents" / agent
            available = {c["hash"]: c for c in raw["commits"][agent]}
            following = []
            for candidate in entry["eligible_after_own_receipt"]:
                full = next(h for h in available if h.startswith(candidate["hash"]))
                following.append(
                    {
                        **available[full],
                        "diff": git(source, "show", "--format=", full),
                        "parents": git(source, "show", "-s", "--format=%P", full).strip(),
                    }
                )
            attempts = [a for a in raw["attempts"] if a["agent_id"] == agent]
            agents.append(
                {
                    "agent": agent,
                    "in_origin_window": agent
                    in {a["agent"] for a in criterion["origin_window"]["staged_attempts"]},
                    "feedback_availability": own,
                    "subsequent_commits": following,
                    "attempt_feedback": [
                        {
                            "commit": a["commit_hash"],
                            "timestamp": a["timestamp"],
                            "feedback": a["feedback"],
                        }
                        for a in attempts
                    ],
                    "online_scores": entry["trajectory"],
                }
            )
        chains.append(
            {
                "name": criterion["name"],
                "task": criterion["task"],
                "description": criterion["description"],
                "cited_evidence": criterion["cited_evidence"],
                "published_at": criterion["published_at"],
                "origin_window": criterion["origin_window"],
                "public_notes": criterion["public_notes_naming_it"],
                "agents": agents,
            }
        )
    (out / "source_chains.json").write_text(json.dumps(chains, indent=2) + "\n")
    print(
        f"Extracted {len(chains)} criteria and their complete subsequent commit diffs.", flush=True
    )
    if not args.browser:
        return
    from playwright.sync_api import sync_playwright

    probes = (
        (
            "captain-ahab",
            "a0a2bd8e7f82c241c6d0464207ac02c2b3b260ef",
            "90fc6a541ccf5137b36368e60fab0dcbc52d3003",
            ".exhibition-overlay.active",
            {"container1", "container2", "container3", "programBtn"},
        ),
        (
            "davy-jones",
            "c8d849b614d2c7fd47b3f9307e75d86fe9aa2402",
            "07d5a7ed991c1235c6cd6b5b16a4f1748c64fe75",
            ".modal.active",
            set(),
        ),
    )
    museum_run = json.loads((HERE / "raw" / "museum_adaptive.json").read_text())["run_dir"]
    results = []
    with (
        tempfile.TemporaryDirectory(prefix="coral-response-probes-") as temporary,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch()
        try:
            for agent, before, after, overlay, ids in probes:
                source = args.results / museum_run / "agents" / agent
                for phase, commit in (("before", before), ("after", after)):
                    stage = Path(temporary) / agent / phase
                    stage.mkdir(parents=True)
                    (stage / "index.html").write_text(git(source, "show", f"{commit}:index.html"))
                    server = _serve(stage)
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    page = context.new_page()
                    trace = out / f"keyboard_{agent}_{phase}.zip"
                    context.tracing.start(screenshots=True, snapshots=True)
                    visited = []
                    activations = []
                    try:
                        page.goto(server.url, wait_until="domcontentloaded")
                        page.wait_for_timeout(800)
                        for _ in range(16):
                            page.keyboard.press("Tab")
                            active = page.evaluate(
                                "() => ({tag:document.activeElement.tagName,id:document.activeElement.id,text:document.activeElement.innerText?.slice(0,120),cls:document.activeElement.className})"
                            )
                            visited.append(active)
                            target = (
                                active["id"] in ids
                                if ids
                                else "exhibition-card" in active.get("cls", "")
                            )
                            identity = active["id"] or active.get("cls")
                            if target and not any(a["control"] == identity for a in activations):
                                page.keyboard.press("Enter")
                                page.wait_for_timeout(200)
                                opened = page.locator(overlay).count() > 0
                                if opened:
                                    page.screenshot(
                                        path=str(out / f"keyboard_{agent}_{phase}_{identity}.png")
                                    )
                                page.keyboard.press("Escape")
                                page.wait_for_timeout(200)
                                activations.append(
                                    {
                                        "control": identity,
                                        "enter_opened": opened,
                                        "escape_dismissed": opened
                                        and page.locator(overlay).count() == 0,
                                    }
                                )
                                if opened and page.locator(overlay).count() > 0:
                                    break
                        results.append(
                            {
                                "agent": agent,
                                "phase": phase,
                                "commit": commit,
                                "tab_sequence": visited,
                                "activations": activations,
                                "limit": "16 Tab presses at desktop; specific controls only; Enter/Escape, not a full accessibility audit",
                            }
                        )
                    finally:
                        context.tracing.stop(path=str(trace))
                        context.close()
                        server.shutdown()
        finally:
            browser.close()
    (out / "keyboard_reproductions.json").write_text(json.dumps(results, indent=2) + "\n")
    for row in results:
        print(row["agent"], row["phase"], row["activations"], flush=True)


if __name__ == "__main__":
    main()
