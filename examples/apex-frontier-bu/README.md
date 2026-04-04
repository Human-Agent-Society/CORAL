# Frontier BU Revenue and Profit Forecast — APEX-Agents (MCP + Agent Judge)

## Origin

Adapted from the APEX-Agents benchmark (mercor/apex-agents on HuggingFace).
- **Task ID**: `task_a89f67b98b5e468d8d5f2a359db895d6`
- **Task Name**: `World 128_RG_01`
- **World**: Management Consulting World 128 — Amensa Global strategic evaluation
- **Domain**: Management Consulting

## What's Different from `apex-frontier/`

This version uses the **original APEX file formats** (.xlsx, .pdf, .docx) accessed
via **Archipelago MCP servers**, rather than pre-extracted markdown. This is faithful
to the original benchmark where agents navigate 21+ source files using structured
spreadsheet, document, and PDF tools.

It also uses the **agent judge grader** — a spawned agent that evaluates output
with tool access (including the same MCP tools), generates its own rubric criteria,
and evolves them autonomously.

## Setup

### 1. Download source files from HuggingFace

```bash
pip install datasets huggingface_hub
python examples/apex-frontier-bu/download_apex_data.py
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
coral start -c examples/apex-frontier-bu/task.yaml
```

## Files

```
examples/apex-frontier-bu/
├── README.md                    # This file
├── task.yaml                    # Agent judge + MCP servers config
├── repo/                        # Source files (populated by download script)
│   └── analysis.md              # Placeholder — agent overwrites
├── eval/                        # Reference materials for grader
└── download_apex_data.py        # Fetches original files from HuggingFace
```
