
<div align="center">

<img src="assets/logo.png" alt="CORAL logo — multi-agent autonomous coding infrastructure" width="360">

## Robust, lightweight infrastructure for multi-agent self-evolution, built for autoresearch.

[![Paper](https://img.shields.io/badge/Paper-arXiv%3A2604.01658-B31B1B.svg?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.01658v1)
[![Blog](https://img.shields.io/badge/Blog-CORAL-FF6B6B.svg?logo=hashnode&logoColor=white)](https://human-agent-society.github.io/CORAL/)
[![Apache 2.0 License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)

**English** | [中文](README_CN.md)

</div>

<p align="center">
<a href="#installation">Installation</a> · <a href="#supported-agents">Supported Agents</a> · <a href="#how-it-works">How It Works</a> · <a href="#examples">Examples</a> · <a href="https://docs.coralxyz.com/">Docs</a> · <a href="https://arxiv.org/abs/2604.01658v1">Paper</a>
</p>

**CORAL** is infrastructure for **autonomous AI agent organizations** that run experiments, share knowledge, and continuously improve solutions. Give it a codebase and a grader, and CORAL handles the rest: isolated workspaces, safe evaluation, persistent shared state, and multi-agent collaboration. Natively integrated with Claude Code, OpenCode, Codex, Cursor Agent, and Kiro.

### 🔥 News

- **[2026-04-24]** Rubric judges — two reusable LLM-judge grader packages for open-ended tasks (reports, memos, legal analysis). See the [Rubric Judges guide](https://docs.coralxyz.com/guides/rubric-judge).
- [Older news →](https://docs.coralxyz.com/blog)

![CORAL demo — autonomous AI coding agents running in parallel git worktrees, sharing knowledge through a common state directory](assets/demo.gif)

### Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
```

Installs `coral` globally via `uv tool install`. Pin a version with `CORAL_VERSION=v0.5.0`. See [Installation docs](https://docs.coralxyz.com/getting-started/installation) for manual install, dev setup, and prerequisites.

```bash
coral init my-task                       # scaffold a task
cd my-task && coral start -c task.yaml   # launch agents
```

### Supported Agents

| Agent | `agents.runtime` |
|-------|------------------|
| [Claude Code](https://github.com/anthropics/claude-code) — default | `claude_code` |
| [Codex](https://github.com/openai/codex) | `codex` |
| [Cursor Agent](https://cursor.com/docs/cli/overview) | `cursor` |
| [Kiro](https://kiro.dev) | `kiro` |
| [OpenCode](https://github.com/opencode-ai/opencode) | `opencode` |

Each agent must be installed and authenticated separately. Per-runtime config — including the [LiteLLM gateway](https://docs.coralxyz.com/guides/gateway) for custom models — is documented at [Agent Runtimes](https://docs.coralxyz.com/guides/agent-runtimes).

### How It Works

<p align="center">
  <img src="assets/coral_diagram_trans.jpg" alt="CORAL architecture diagram: multiple coding agents run in isolated git worktrees, share state via .coral/public/, and are scored by a grader daemon" width="800">
</p>

Each agent runs in its own git worktree. Shared state (attempts, notes, skills) lives in `.coral/public/` and is symlinked into every worktree — agents see each other's work in real time. A grader daemon scores every commit. The manager interrupts agents with heartbeat prompts (`reflect`, `consolidate`, `pivot`).

Deeper dive: [Concepts](https://docs.coralxyz.com/concepts) · [Multi-agent runs](https://docs.coralxyz.com/guides/multi-agent) · [Eval loop](https://docs.coralxyz.com/concepts/eval-loop)

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

Full catalogue and walkthroughs at [Examples docs](https://docs.coralxyz.com/examples).

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
