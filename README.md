
<div align="center">

<img src="assets/logo.png" alt="Coral" width="360">


#### Robust, lightweight infrastructure for multi-agent self-evolution, built for autoresearch.

## 🚀 Supercharge Your AutoResearch



[![Paper](https://img.shields.io/badge/Paper-arXiv%3A2604.01658-B31B1B.svg?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.01658v1)
[![Blog](https://img.shields.io/badge/Blog-CORAL-FF6B6B.svg?logo=hashnode&logoColor=white)](https://human-agent-society.github.io/CORAL/)
[![Apache 2.0 License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-5C4EE5.svg)](https://docs.astral.sh/uv/)

**English** | [中文](README_CN.md)

</div>

<p align="center">
<a href="#installation">Installation</a> · <a href="#supported-agents">Supported Agents</a> · <a href="#usage">Usage</a> · <a href="#how-it-works">How It Works</a> · <a href="#examples">Examples</a> · <a href="https://human-agent-society.github.io/CORAL/">Docs</a> · <a href="#license">License</a>
</p>


**CORAL** is an infrastructure for building organizations of **autonomous AI agents** that run experiments, share knowledge, and continuously improve solutions. Give it a codebase and a grading script, and Coral handles the rest: isolated workspaces, safe evaluation, persistent shared knowledge, and multi-agent collaboration to enable robust evolution. Coral is natively integrated with Claude Code, OpenCode, Codex, and other major coding agents.

Want self-improving AI without the configuration overhead? Try Coral.



### 🔥 News!

- **[2026-04-24]** **Rubric judges** — two reusable LLM-judge grader packages for open-ended tasks (reports, memos, legal analysis). Static rubrics (`race_japan_grader`) and auto-evolving dynamic rubrics (`apex_judge`), both spawning Claude Code as the judge. See the [Rubric Judges guide](docs/content/docs/guides/rubric-judge.mdx) and the new `examples/race-japan-elderly/`, `examples/apex-eggshell-skull/`, `examples/apex-frontier-bu/` tasks.
- **[2026-04-03]** Our paper, “CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery,” is now out! Check it out on [Arxiv](https://arxiv.org/pdf/2604.01658).
- **[2026-03-18]** CORAL is released! Check out our [blog post](https://human-agent-society.github.io/CORAL/).

![Demo](assets/demo.gif)

### Installation

**One line — installs `coral` globally so you can run it from any directory:**

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
```

The script bootstraps [`uv`](https://github.com/astral-sh/uv) if missing, then runs `uv tool install` to drop the `coral` binary into `~/.local/bin`. Pin a version by setting `CORAL_VERSION=v0.5.0` (any git tag/branch/commit works).

<details>
<summary>Manual install (skip the curl pipe)</summary>

```bash
# Already have uv? One command:
uv tool install git+https://github.com/Human-Agent-Society/CORAL.git

# Install / upgrade uv first if needed:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

</details>

<details>
<summary>Develop CORAL itself (clone + editable install)</summary>

```bash
git clone https://github.com/Human-Agent-Society/CORAL.git
cd CORAL
uv sync                       # (add --extra ui for the dashboard, --extra dev for tests)
uv run coral --help           # prefix commands with `uv run` in the dev checkout
```

</details>

Verify:

```bash
coral --version
```

### Supported Agents

Coral works with any coding agent that can run as a subprocess and interact via the terminal. Currently supported:

| Agent | Description |
|-------|-------------|
| [**Claude Code**](https://github.com/anthropics/claude-code) | Anthropic's agentic coding tool — the default and most tested runtime |
| [**Codex**](https://github.com/openai/codex) | OpenAI's open-source coding agent |
| [**Cursor Agent**](https://cursor.com/docs/cli/overview) | Cursor's headless `cursor-agent` CLI |
| [**Kiro**](https://kiro.dev) | Kiro's `kiro-cli` agent (AWS-hosted) |
| [**OpenCode**](https://github.com/opencode-ai/opencode) | Open-source terminal-based AI coding agent |

> [!TIP]
> Before using Coral, make sure you have fully set up the agent(s) you plan to use:
>
> - **Install the Agent:** Follow the official installation instructions for your agent (e.g., Claude Code, Codex, OpenCode). This may involve installing packages, setting up executables, or configuring scripts.
> - **Authentication:** Login and authenticate your coding agent first to make sure they do not ask for your credentials in CLI mode. Set up any required environment variables, configuration files, or authentication secrets as specified in your agent's documentation.
> - **Set Permissions:** Configure your agent's permission settings via its config file (e.g., `~/.claude/settings.json` for Claude Code) to control which tools, file paths, or actions it is allowed to perform.
>
> *Coral does not handle agent installation or authentication for you. The infrastructure will fail to function if the underlying agent cannot start or is not properly authenticated.*

Set the agent in your task config (refer to <a href="#3-configure-the-task">Configure the task</a>):

```yaml
agents:
  runtime: claude_code   # or "codex", "cursor", "kiro", "opencode"
  count: 3  # how many agents you want to spawn. Beware of your budget :)
  model: opus   # name of the model you wish to use
```

### Usage

```bash
# start a run
coral start -c examples/kernel_builder/task.yaml

# override any config value via dotlist syntax
coral start -c task.yaml agents.count=4 agents.model=opus
coral start -c task.yaml run.verbose=true        # stream agent output
coral start -c task.yaml run.ui=true             # also launch web dashboard

# stop and resume
coral stop                                       # stop anytime
coral resume                                     # pick up where you left off

# monitor progress
coral status                                     # CLI leaderboard
coral ui                                         # web dashboard
```

Full CLI reference: see [`coral --help`](https://human-agent-society.github.io/CORAL/cli/reference) or run `coral --help`. Configuration options (warm-start, gateway, Docker session, etc.) live in the [Configuration](https://human-agent-society.github.io/CORAL/getting-started/configuration) docs.

### How It Works

<p align="center">
  <img src="assets/coral_diagram_trans.jpg" alt="Coral Architecture Diagram" width="800">
</p>

Each agent runs in its own git worktree branch. Shared state (attempts, notes, skills) lives in `.coral/public/` and is symlinked into every worktree — agents see each other's work in real time with zero sync overhead. The manager watches for new attempts and can interrupt agents with heartbeat-triggered prompts (e.g. "reflect", "consolidate skills").

| Concept | Description |
|---------|-------------|
| **Agents as optimizers** | Claude Code / Codex / Cursor Agent / Kiro / OpenCode subprocesses, each in its own git worktree |
| **Shared state** | `.coral/` directory with attempts, notes, and skills — symlinked into every worktree |
| **Eval loop** | Agents call `coral eval -m "..."` to stage, commit, and grade in one shot |
| **CLI orchestration** | 17+ commands: `start`, `stop`, `status`, `eval`, `log`, `ui`, and more |
| **Web dashboard** | `coral ui` — real-time leaderboard, attempt diffs, agent monitoring |

**Deep research:** Agents come with a bundled `deep-research` skill that guides structured literature review — web search, saving raw sources, writing research notes, and building an index. It runs automatically during warm-start (`agents.warmstart.enabled=true`), and agents can also invoke it mid-run when pivoting to a new approach. Requires `agents.research=true` for web search.

### Quick Start

Three commands get you running:

```bash
coral init my-task                            # scaffold task.yaml + grader stub + seed/
# edit my-task/task.yaml and my-task/eval/grader.py for your problem
coral validate my-task                        # dry-run the grader against seed/
coral start -c my-task/task.yaml              # launch agents (auto-tmux)
```

Want a complete walkthrough — seed code, grader, task.yaml, launch — with a worked TSP example? See the [Quick Start guide](https://human-agent-society.github.io/CORAL/getting-started/quickstart).

### Agent Runtimes & Gateway

Claude Code (the default) needs no special config beyond an Anthropic API key. To use a different runtime, see the per-runtime guides:

- [OpenCode](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#opencode) — requires an `opencode.json` in your seed directory
- [Cursor Agent](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#cursor-agent) — `cursor-agent login` once, then set `runtime: cursor`
- [Kiro](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#kiro) — `kiro-cli` install + setup, then `runtime: kiro`

To route agent traffic through a unified proxy (custom models, request logging, per-agent keys), enable the built-in [LiteLLM Gateway](https://human-agent-society.github.io/CORAL/guides/gateway).

### Examples

Ready-to-run task configurations in `examples/`:


| Task                       | Domain       | Description                                                 |
| -------------------------- | ------------ | ----------------------------------------------------------- |
| **circle_packing**         | Optimization | Pack 26 circles into a unit square to maximize sum of radii |
| **erdos**                  | Mathematics  | Solve a math conjecture                                     |
| **kernel_builder**         | Systems      | VLIW SIMD kernel optimization                               |
| **kernel_engineering**     | Systems      | GPU kernel optimization                                     |
| **mnist**                  | ML           | Handwritten digit classification                            |
| **spaceship_titanic**      | ML           | Kaggle competition                                          |
| **stanford_covid_vaccine** | Bio/ML       | mRNA degradation prediction                                 |


### Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Lint & format
uv run ruff check .
uv run ruff format .
```

> [!IMPORTANT]
> **Docker requirement:** Some built-in graders (e.g. SWE-bench, terminal-bench) use [Harbor](https://github.com/corca-ai/harbor) to run evaluations inside Docker containers. CORAL itself must **not** run inside Docker in this case, as Docker-in-Docker (DinD) is not supported. Run CORAL directly on the host machine.

This project is released under the Apache 2.0 [LICENSE](LICENSE).


### Citation

⭐ If you find CORAL useful, please consider giving us a Star and/or citing it in your work (Please use the official BibTeX below instead of Google Scholar’s auto-generated citation, which may truncate the author list):

```bibtex
@article{qu2026coral,
  title={CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery},
  author={Qu, Ao and Zheng, Han and Zhou, Zijian and Yan, Yihao and Tang, Yihong and Ong, Shao Yong and Hong, Fenglu and Zhou, Kaichen and Jiang, Chonghe and Kong, Minwei and Zhu, Jiacheng and Jiang, Xuan and Li, Sirui and Wu, Cathy and Low, Bryan Kian Hsiang and Zhao, Jinhua and Liang, Paul Pu},
  journal={arXiv preprint arXiv:2604.01658},
  year={2026}
}
```

<a href="https://www.star-history.com/?repos=Human-Agent-Society%2FCoral&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Human-Agent-Society/Coral&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Human-Agent-Society/Coral&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Human-Agent-Society/Coral&type=date&legend=top-left" />
 </picture>
</a>

### Acknowledgement

We thank the [TNT Accelerator](https://www.tnt.so/) for their generous support of various API credits that have helped during the development of Coral. We would also like to thank many of the inspiring prior works such as [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve), [autoresearch](https://github.com/karpathy/autoresearch), [TTT Discover](https://arxiv.org/abs/2601.16175),  etc., that have led to the ideation of Coral.
