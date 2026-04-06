#!/usr/bin/env python3
"""Download original APEX-Agents source files for the eggshell skull task.

Fetches world files and task-specific files from the mercor/apex-agents
HuggingFace dataset and places them in the repo/ directory.

Requirements:
    pip install huggingface_hub

Usage:
    python examples/apex-eggshell-skull/download_apex_data.py
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

TASK_ID = "task_b5481555a1c94da6bf78baf87165851c"
WORLD_ID = "world_06051b9b10c94c079db1bac3b70c4c4b"
DATASET_REPO = "mercor/apex-agents"
REPO_DIR = Path(__file__).parent / "repo"


def main() -> None:
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError:
        print("Error: 'huggingface_hub' package not installed.")
        print("Run: pip install huggingface_hub")
        sys.exit(1)

    api = HfApi()
    REPO_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Download and extract the world zip (shared files for this world)
    world_zip_path = f"world_files_zipped/{WORLD_ID}.zip"
    print(f"Downloading world files: {world_zip_path}")
    try:
        local_zip = hf_hub_download(
            repo_id=DATASET_REPO,
            filename=world_zip_path,
            repo_type="dataset",
        )
        print(f"Extracting world zip to {REPO_DIR}...")
        with zipfile.ZipFile(local_zip, "r") as zf:
            zf.extractall(REPO_DIR)
        world_files = sum(1 for _ in REPO_DIR.rglob("*") if _.is_file())
        print(f"  Extracted {world_files} files from world zip")
    except Exception as e:
        print(f"Failed to download world zip: {e}")
        print("Make sure you're logged in: huggingface-cli login")
        print(f"And have accepted the license at: https://huggingface.co/datasets/{DATASET_REPO}")
        sys.exit(1)

    # 2. Download task-specific files
    task_prefix = f"task_files/{TASK_ID}/filesystem"
    print(f"\nDownloading task-specific files from: {task_prefix}/")
    try:
        task_files = list(api.list_repo_tree(
            DATASET_REPO, repo_type="dataset",
            path_in_repo=task_prefix, recursive=True,
        ))
        task_file_count = 0
        for f in task_files:
            rfilename = f.rfilename if hasattr(f, "rfilename") else None
            if rfilename is None or not hasattr(f, "size"):
                continue  # skip directories
            # Download the file
            local_path = hf_hub_download(
                repo_id=DATASET_REPO,
                filename=rfilename,
                repo_type="dataset",
            )
            # Place it in repo/ with just the filename (strip the prefix path)
            relative = rfilename[len(task_prefix) + 1:]  # strip "task_files/.../filesystem/"
            dest = REPO_DIR / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(local_path, dest)
            print(f"  {relative} ({f.size} bytes)")
            task_file_count += 1
        print(f"  Downloaded {task_file_count} task-specific files")
    except Exception as e:
        print(f"Warning: Could not download task-specific files: {e}")

    # Summary
    total_files = sum(1 for _ in REPO_DIR.rglob("*") if _.is_file())
    print(f"\nDone! {total_files} total files in {REPO_DIR}")

    # List key files
    print("\nFiles in repo/:")
    for f in sorted(REPO_DIR.rglob("*")):
        if f.is_file():
            rel = f.relative_to(REPO_DIR)
            print(f"  {rel} ({f.stat().st_size:,} bytes)")

    # Check for Archipelago
    archipelago_path = os.environ.get("ARCHIPELAGO_PATH", "")
    if not archipelago_path or not Path(archipelago_path).exists():
        print("\n--- Archipelago Setup ---")
        print("The MCP servers require the Archipelago repository.")
        print("Clone it and set the ARCHIPELAGO_PATH environment variable:")
        print()
        print("  git clone https://github.com/Mercor-Intelligence/archipelago.git")
        print("  export ARCHIPELAGO_PATH=/path/to/archipelago")
        print()
        print("Then install each MCP server's dependencies:")
        print("  cd $ARCHIPELAGO_PATH/mcp_servers/spreadsheets && uv sync --all-extras")
        print("  cd $ARCHIPELAGO_PATH/mcp_servers/documents && uv sync --all-extras")
        print("  cd $ARCHIPELAGO_PATH/mcp_servers/pdfs && uv sync --all-extras")
        print("  cd $ARCHIPELAGO_PATH/mcp_servers/filesystem && uv sync --all-extras")


if __name__ == "__main__":
    main()
