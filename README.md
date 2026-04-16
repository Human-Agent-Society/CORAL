
<div align="center">

<img src="assets/logo.png" alt="Coral" width="360">


#### Robust, lightweight infrastructure for multi-agent self-evolution, built for autoresearch.

## 🚀 Supercharge Your AutoResearch



[![Paper](https://img.shields.io/badge/Paper-arXiv%3A2604.01658-B31B1B.svg?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.01658v1)
[![Blog](https://img.shields.io/badge/Blog-CORAL-FF6B6B.svg?logo=hashnode&logoColor=white)](https://human-agent-society.github.io/CORAL/)
[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-5C4EE5.svg)](https://docs.astral.sh/uv/)

**English** | [中文](README_CN.md)

</div>

<p align="center">
<a href="#installation">Installation</a> · <a href="#supported-agents">Supported Agents</a> · <a href="#usage">Usage</a> · <a href="#how-it-works">How It Works</a> · <a href="#quick-start">Quick Start</a> · <a href="#cli-reference">CLI Reference</a> · <a href="#using-opencode">OpenCode</a> · <a href="#using-the-gateway-for-custom-models">Gateway</a> · <a href="#examples">Examples</a> · <a href="#license">License</a>
</p>


**CORAL** is an infrastructure for building organizations of **autonomous AI agents** that run experiments, share knowledge, and continuously improve solutions. Give it a codebase and a grading script, and Coral handles the rest: isolated workspaces, safe evaluation, persistent shared knowledge, and multi-agent collaboration to enable robust evolution. Coral is natively integrated with Claude Code, OpenCode, Codex, and other major coding agents.

Want self-improving AI without the configuration overhead? Try Coral.



### 🔥 News!

- **[2026-04-03]** Our paper, “CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery,” is now out! Check it out on [Arxiv](https://arxiv.org/pdf/2604.01658).
- **[2026-03-18]** CORAL is released! Check out our [blog post](https://human-agent-society.github.io/CORAL/).

![Demo](assets/demo.gif)

### Installation

```bash
git clone https://github.com/Human-Agent-Society/CORAL.git
cd CORAL
# install uv from https://github.com/astral-sh/uv
uv sync                   # (optionally add --extra ui to include dashboard dependencies)
```

### Supported Agents

Coral works with any coding agent that can run as a subprocess and interact via the terminal. Currently supported:

| Agent | Description |
|-------|-------------|
| [**Claude Code**](https://github.com/anthropics/claude-code) | Anthropic's agentic coding tool — the default and most tested runtime |
| [**Codex**](https://github.com/openai/codex) | OpenAI's open-source coding agent |
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
  runtime: claude_code   # or "codex" or "opencode"
  count: 3  # how many agents you want to spawn. Beware of your budget :)
  model: opus   # name of the model you wish to use
```

### Usage

```bash
# start a run
uv run coral start -c examples/kernel_builder/task.yaml

# override any config value via dotlist syntax
uv run coral start -c task.yaml agents.count=4 agents.model=opus
uv run coral start -c task.yaml run.verbose=true        # stream agent output
uv run coral start -c task.yaml run.ui=true              # also launch web dashboard
uv run coral start -c task.yaml run.session=local         # skip tmux, run inline
uv run coral start -c task.yaml run.session=docker        # run inside Docker container

# warm-start: research phase before coding (agents do literature review first)
uv run coral start -c task.yaml agents.warmstart.enabled=true agents.research=true

# stop and resume
uv run coral stop                                        # stop anytime
uv run coral resume                                      # pick up where you left off
uv run coral resume agents.model=opus run.verbose=true   # resume with overrides

# monitor progress
uv run coral ui                                          # open the web dashboard
```

### How It Works

<p align="center">
  <img src="assets/coral_diagram_trans.jpg" alt="Coral Architecture Diagram" width="800">
</p>

Each agent runs in its own git worktree branch. Shared state (attempts, notes, skills) lives in `.coral/public/` and is symlinked into every worktree — agents see each other's work in real time with zero sync overhead. The manager watches for new attempts and can interrupt agents with heartbeat-triggered prompts (e.g. "reflect", "consolidate skills").

| Concept | Description |
|---------|-------------|
| **Agents as optimizers** | Claude Code / Codex / OpenCode subprocesses, each in its own git worktree |
| **Shared state** | `.coral/` directory with attempts, notes, and skills — symlinked into every worktree |
| **Eval loop** | Agents call `uv run coral eval -m "..."` to stage, commit, and grade in one shot |
| **CLI orchestration** | 17+ commands: `start`, `stop`, `status`, `eval`, `log`, `ui`, and more |
| **Web dashboard** | `uv run coral ui` — real-time leaderboard, attempt diffs, agent monitoring |

**Deep research:** Agents come with a bundled `deep-research` skill that guides structured literature review — web search, saving raw sources, writing research notes, and building an index. It runs automatically during warm-start (`agents.warmstart.enabled=true`), and agents can also invoke it mid-run when pivoting to a new approach. Requires `agents.research=true` for web search.

### Quick Start

Let's walk through a complete example: agents continually optimize a **100-city Traveling Salesman Problem**.

#### 1. Write a seed codebase

The seed is the starting code that agents will iterate on. Create a working directory:

```bash
mkdir -p examples/tsp/{seed,eval}
```

Then create a naive initial solution (you can choose to start empty, though it can make the job of the agents harder):

```python
# examples/tsp/seed/solution.py
import random

# Restate the problem here as the agent cannot read the content of `grader.py`
random.seed(42)
CITIES = [(random.random(), random.random()) for _ in range(100)]

# Naive: visit cities in index order (0, 1, 2, ..., 99)
for i in range(len(CITIES)):
    print(i)
```

#### 2. Write a grader

Subclass `TaskGrader` and implement `evaluate()`. The base class provides two helpers: `self.run_program(filename)` which runs a file from the agent's codebase in a subprocess and returns a `CompletedProcess` (with `.stdout`, `.stderr`, `.returncode`), and `self.fail(reason)` which records the failure and returns a null score:

```python
# examples/tsp/eval/grader.py
import math
import random
from coral.grader import TaskGrader, ScoreBundle

# keep consistent with the problem statement in `solution.py`
random.seed(42)
CITIES = [(random.random(), random.random()) for _ in range(100)]

class Grader(TaskGrader):
    def evaluate(self) -> float | ScoreBundle:
        try:
            result = self.run_program("solution.py")  # runs solution.py, returns CompletedProcess
            order = [int(x) for x in result.stdout.strip().split("\n")]
            assert sorted(order) == list(range(len(CITIES)))
            dist = sum(
                math.dist(CITIES[order[i]], CITIES[order[(i + 1) % len(order)]])
                for i in range(len(order))
            )
            return -dist  # shorter tour = higher score
        except Exception as e:
            return self.fail(str(e))  # records failure and returns null score
```

The naive seed tour scores about `-58.02`. Agents will try nearest-neighbor, 2-opt, simulated annealing, etc. to find shorter routes. With 100 cities, exhaustive search is completely infeasible (99! permutations), so agents must discover and apply real optimization heuristics.

#### 3. Configure the task

Point the config at your seed codebase and grader:

```yaml
# examples/tsp/task.yaml
task:
  name: tsp
  description: |
    Find the shortest round-trip tour through 100 cities. The coordinates
    are generated via numpy with a fixed seed in `solution.py`. DO NOT MODIFY the seed or CITIES generation!

    solution.py must print 100 integers (0-99) to stdout, one per line,
    representing the visit order. Each city must appear exactly once.

    The grader computes the total Euclidean round-trip distance
    and returns -distance as the score (shorter = higher).

grader:
  type: function
  module: eval.grader

agents:
  count: 1
  runtime: claude_code  # or opencode, codex
  model: claude-sonnet-4-6
  max_turns: 200  # before the agent reboots. dont worry Coral keeps running until you stop

workspace:
  results_dir: "./results"  # relative to your $PWD
  repo_path: "./examples/tsp/seed"  # relative to your $PWD
```

#### 4. Launch

```bash
uv run coral start -c examples/tsp/task.yaml             # launches in tmux session `coral-tsp`
uv run coral start -c examples/tsp/task.yaml agents.count=4  # override agent count
uv sync --extra ui && uv run coral ui                     # open web dashboard (port 8420)
uv run coral status      # CLI leaderboard
uv run coral log         # View attempts
uv run coral stop        # Stop all agents
```

### CLI Reference

<details>
<summary>Click to expand all 17+ commands</summary>

| Command                              | Description                         |
| ------------------------------------ | ----------------------------------- |
| `uv run coral init <name>`           | Scaffold a new task                 |
| `uv run coral validate <name>`       | Test the grader                     |
| `uv run coral start -c task.yaml [overrides...]` | Launch agents (e.g. `agents.count=4 run.verbose=true`) |
| `uv run coral resume [overrides...]` | Resume a previous run (e.g. `agents.model=opus`)       |
| `uv run coral stop`                  | Stop all agents                     |
| `uv run coral status`                | Agent health + leaderboard          |
| `uv run coral log`                   | Leaderboard (top 20)                |
| `uv run coral log -n 5 --recent`     | Recent attempts                     |
| `uv run coral log --search "query"`  | Search attempts                     |
| `uv run coral show <hash>`           | Attempt details + diff              |
| `uv run coral notes`                 | Browse shared notes                 |
| `uv run coral skills`                | Browse shared skills                |
| `uv run coral runs`                  | List all runs                       |
| `uv run coral ui`                    | Web dashboard                       |
| `uv run coral eval -m "description"` | Stage, commit, evaluate (agent use) |
| `uv run coral diff`                  | Show uncommitted changes            |
| `uv run coral revert`                | Undo last commit                    |
| `uv run coral checkout <hash>`       | Reset to previous attempt           |
| `uv run coral heartbeat`             | View/modify heartbeat actions       |

</details>


### Architecture

<details>
<summary>Click to expand</summary>

```
coral/
├── types.py             # Task, Score, ScoreBundle, Attempt
├── config.py            # YAML-based CoralConfig
├── agent/
│   ├── manager.py       # Multi-agent lifecycle
│   └── runtime.py       # Claude Code / Codex / OpenCode subprocess
├── workspace/
│   └── setup.py         # Worktree creation, hooks, symlinks
├── grader/
│   ├── protocol.py      # GraderInterface protocol
│   ├── base.py          # BaseGrader (helpers: _make_score, _make_bundle)
│   ├── task_grader.py   # TaskGrader for task-specific graders
│   ├── loader.py        # Grader discovery and loading
│   └── builtin/
│       └── function_grader.py
├── hub/
│   ├── attempts.py      # Attempt CRUD + leaderboard + search
│   ├── notes.py         # Markdown notes with YAML frontmatter
│   └── skills.py        # Skill directories with SKILL.md
├── hooks/
│   └── post_commit.py   # Eval-on-commit implementation
├── template/
│   └── coral_md.py      # CORAL.md generator
├── web/                 # Starlette + React dashboard
└── cli/                 # 17 commands across 5 modules
```

</details>

### Using OpenCode

To use [OpenCode](https://github.com/opencode-ai/opencode) as your agent runtime, you need to provide an `opencode.json` configuration file in your seed directory. This file configures OpenCode's permissions and provider settings.

Here is an example from `examples/circle_packing/seed/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "external_directory": "allow",
    "question": "deny",
    "doom_loop": "allow",
    "bash": "allow",
    "edit": "allow",
    "read": "allow",
    "write": "allow",
    "webfetch": "deny",
    "websearch": "deny",
    "codesearch": "allow",
    "lsp": "allow",
    "skill": "allow"
  },
  "provider": {
    "claude": {
      "npm": "@ai-sdk/anthropic",
      "name": "claude",
      "options": {
        "baseURL": "http://localhost:4000/v1",
        "apiKey": "xxx"
      },
      "models": {
        "claude-opus-4-6": {
          "name": "claude-opus-4-6"
        }
      }
    }
  }
}
```

Key points:
- Set all permissions to `"allow"` (except `question`, `webfetch`, `websearch` which should be `"deny"`) so the agent can run autonomously without interactive prompts.
- The `provider` section configures which model to use. When using the gateway (see below), point `baseURL` at `http://localhost:<gateway_port>/v1` and set `apiKey` to any placeholder value — the gateway handles authentication.
- Place `opencode.json` in your seed directory so it gets copied into each agent's worktree.

Then set your task config to use OpenCode:

```yaml
agents:
  runtime: opencode
  model: claude/claude-opus-4-6  # must match a model defined in opencode.json
```

### Using the Gateway for Custom Models

CORAL includes a built-in **LiteLLM gateway** that acts as a proxy between agents and model providers. This is useful when you want to:

- Route agent requests through a single proxy with unified API key management
- Use custom or self-hosted models
- Add request logging and per-agent tracking
- Use providers that require non-standard authentication

#### Setting up the gateway

**1. Create a LiteLLM config file** (e.g. `litellm_config.yaml`) alongside your `task.yaml`:

```yaml
# examples/circle_packing/litellm_config.yaml
model_list:
  - model_name: "claude-opus-4-6"
    litellm_params:
      model: "anthropic/claude-opus-4-6"
      api_key: "YOUR_ANTHROPIC_API_KEY"

litellm_settings:
  drop_params: true
```

Each entry in `model_list` defines a model the gateway will serve. The `model_name` is what agents request; `litellm_params.model` is the upstream provider model. See the [LiteLLM docs](https://docs.litellm.ai/docs/proxy/configs) for full configuration options (multiple providers, load balancing, fallbacks, etc.).

**2. Enable the gateway in your task config:**

```yaml
agents:
  runtime: opencode           # or claude_code, codex
  model: claude/claude-opus-4-6
  gateway:
    enabled: true
    port: 4000                # port the gateway listens on
    config: "./litellm_config.yaml"  # path relative to task.yaml
```

**3. Point your agent at the gateway.** For OpenCode, set `baseURL` in `opencode.json` to `http://localhost:<port>/v1`. For Claude Code, the gateway URL is automatically injected.

When you run `coral start`, the gateway starts before agents are spawned, and all agent API requests are routed through it. The gateway automatically assigns each agent a unique proxy key for per-agent request tracking.

See `examples/circle_packing/` for a complete working example using OpenCode with the gateway.

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

This project is released under MIT [LICENSE](LICENSE).

### Citation

⭐ If you find CORAL useful, please consider giving us a Star and/or citing it in your work:

```bibtex
@article{coral2026,
  title  = {CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery},
  author = {Qu, Ao and Zheng, Han and Zhou, Zijian and Yan, Yihao and Tang, Yihong and Ong, Shao Yong and Hong, Fenglu and Zhou, Kaichen and Jiang, Chonghe and Kong, Minwei and Zhu, Jiacheng and Jiang, Xuan and Li, Sirui and Wu, Cathy and Low, Bryan Kian Hsiang and Zhao, Jinhua and Liang, Paul Pu},
  journal = {arXiv preprint arXiv:2604.01658},
  year   = {2026},
  url    = {https://arxiv.org/pdf/2604.01658}
}
```

### Acknowledgement

We thank the [TNT Accelerator](https://www.tnt.so/) for their generous support of various API credits that have helped during the development of Coral. We would also like to thank many of the inspiring prior works such as [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve), [autoresearch](https://github.com/karpathy/autoresearch), [TTT Discover](https://arxiv.org/abs/2601.16175),  etc., that have led to the ideation of Coral.
