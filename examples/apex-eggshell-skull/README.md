# Eggshell Skull Rule Legal Memorandum — APEX-Agents (MCP + Agent Judge)

## Origin

Adapted from the APEX-Agents benchmark (mercor/apex-agents on HuggingFace).
- **Task ID**: `task_b5481555a1c94da6bf78baf87165851c`
- **Task Name**: `World433_MMF01`
- **World**: Law World 433 — Senior living facility experiencing cutbacks
- **Domain**: Law

## What's Different from `apex-prelim/`

This version uses the **original APEX file formats** (.docx, .pdf) accessed via
**Archipelago MCP servers**, rather than pre-extracted markdown. This is faithful
to the original benchmark where agents navigate multiple files using structured tools.

It also uses the **`apex_judge` grader** — a standalone package shipped under
[`grader/`](grader/) that spawns a judge agent to evaluate the output with tool
access, generate its own rubric criteria, and evolve them autonomously. The
grader is wired via `grader.entrypoint = "apex_judge.grader:Grader"` and
installed into an isolated venv at runtime by `grader.setup`.

## Setup

### 1. Download source files from HuggingFace

```bash
pip install datasets huggingface_hub
python examples/apex-eggshell-skull/download_apex_data.py
```

### 2. Clone and install Archipelago MCP servers

```bash
git clone https://github.com/Mercor-Intelligence/archipelago.git
export ARCHIPELAGO_PATH=/path/to/archipelago

# Install each MCP server
cd $ARCHIPELAGO_PATH/mcp_servers/spreadsheets && mise run install
cd $ARCHIPELAGO_PATH/mcp_servers/documents && mise run install
cd $ARCHIPELAGO_PATH/mcp_servers/pdfs && mise run install
cd $ARCHIPELAGO_PATH/mcp_servers/filesystem && mise run install
```

### 3. Run

```bash
export ARCHIPELAGO_PATH=/path/to/archipelago
coral start -c examples/apex-eggshell-skull/task.yaml
```

## Files

```
examples/apex-eggshell-skull/
├── README.md                    # This file
├── task.yaml                    # Wires apex_judge grader via entrypoint
├── grader/                      # apex_judge standalone package
│   ├── pyproject.toml
│   └── src/apex_judge/
├── repo/                        # Source files (populated by download script)
│   └── memorandum.md            # Placeholder — agent overwrites
├── eval/                        # Reference materials for grader
└── download_apex_data.py        # Fetches original files from HuggingFace
```
