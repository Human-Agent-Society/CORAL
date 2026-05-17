
<div align="center">

<img src="assets/logo.png" alt="CORAL" width="360">

### **一键启动智能体群组，共享知识，无限进化**

<p>
  <img src="assets/mit_logo.png" alt="MIT" height="50">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/nus.png" alt="NUS" height="50">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/stanford.png" alt="Stanford" height="50">
</p>

[![Blog](https://img.shields.io/badge/Blog-CORAL-FF6B6B.svg?logo=hashnode&logoColor=white)](https://human-agent-society.github.io/CORAL/)
[![Apache 2.0 License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-5C4EE5.svg)](https://docs.astral.sh/uv/)

[English](README.md) | **中文**

</div>


<p align="center">
<a href="#安装">安装</a> · <a href="#支持的-agent">支持的 Agent</a> · <a href="#使用">使用</a> · <a href="#工作原理">工作原理</a> · <a href="#示例">示例</a> · <a href="https://human-agent-society.github.io/CORAL/">文档</a> · <a href="#许可证">许可证</a>
</p>

**CORAL** 是一套用于构建**自主 AI Agent 组织**的基础设施，Agent 们持续运行实验、共享知识、不断进化出更优方案。只需提供代码库和评分脚本，Coral 即可完成剩余工作：隔离工作空间、安全评估、持久化共享知识，以及多 Agent 协作驱动持续进化。原生集成 Claude Code、Codex、Cursor Agent、Kiro、OpenCode 等主流编程 Agent。

想要自我进化的 AI，又不想折腾配置？试试 Coral。



### 🔥 News!

- **[2026-04-24]** 新增 **Rubric 评审 (Rubric Judges)** —— 两个开箱即用的 LLM 评审 grader 包，专为开放式任务（报告、备忘、法律分析等）设计：静态评审准则 (`race_japan_grader`) 与可自演进的动态准则 (`apex_judge`)，均由 Claude Code 作为评审代理执行。详见 [Rubric Judges 文档](docs/content/docs/guides/rubric-judge.mdx) 以及新增的 `examples/race-japan-elderly/`、`examples/apex-eggshell-skull/`、`examples/apex-frontier-bu/` 任务。
- **[2026-03-18]** CORAL 正式发布！点击查看[Blog](https://human-agent-society.github.io/CORAL/)。

![Demo](assets/demo.gif)

### 安装

**一行命令 —— 全局安装 `coral`，在任意目录下都可直接调用：**

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
```

该脚本会先检查并按需安装 [`uv`](https://github.com/astral-sh/uv)，然后通过 `uv tool install` 将 `coral` 可执行文件放入 `~/.local/bin`。如需指定版本,设置 `CORAL_VERSION=v0.5.0`(支持任意 git tag/分支/commit)。

<details>
<summary>手动安装（不使用 curl 管道）</summary>

```bash
# 已安装 uv,只需一条命令:
uv tool install git+https://github.com/Human-Agent-Society/CORAL.git

# 若未安装 uv,先安装 uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

</details>

<details>
<summary>参与 CORAL 开发（clone + 可编辑安装）</summary>

```bash
git clone https://github.com/Human-Agent-Society/CORAL.git
cd CORAL
uv sync                       # （添加 --extra ui 包含看板依赖；--extra dev 包含测试工具）
uv run coral --help           # 开发模式下需要加 `uv run` 前缀
```

</details>

验证安装：

```bash
coral --version
```

### 支持的 Agent

CORAL 支持任何可以作为子进程运行并通过终端交互的编程 Agent。目前支持：

| Agent | 说明 |
|-------|------|
| [**Claude Code**](https://github.com/anthropics/claude-code) | Anthropic 的 Agentic 编程工具——默认且测试最充分的运行时 |
| [**Codex**](https://github.com/openai/codex) | OpenAI 的开源编程 Agent |
| [**Cursor Agent**](https://cursor.com/docs/cli/overview) | Cursor 的无头 `cursor-agent` CLI |
| [**Kiro**](https://kiro.dev) | Kiro 的 `kiro-cli` Agent（AWS 托管） |
| [**OpenCode**](https://github.com/opencode-ai/opencode) | 开源终端 AI 编程 Agent |

> [!TIP]
> 在使用 CORAL 之前，请确保已完整配置好你计划使用的 Agent：
>
> - **安装 Agent：** 按照对应 Agent 的官方安装说明进行安装（如 Claude Code、Codex、OpenCode），可能涉及安装包、配置可执行文件或脚本。
> - **身份验证：** 提前登录并完成 Agent 的身份验证，确保其在 CLI 模式下不会弹出凭据请求。按照 Agent 文档配置所需的环境变量、配置文件或认证密钥。
> - **权限设置：** 通过 Agent 的配置文件（如 Claude Code 的 `~/.claude/settings.json`）配置权限，控制 Agent 可以使用的工具、访问的路径或执行的操作。
>
> *CORAL 不负责 Agent 的安装或身份验证。如果底层 Agent 无法启动或未正确完成认证，基础设施将无法正常运行。*

在任务配置中指定 Agent（参见 <a href="#3-配置任务">配置任务</a>）：

```yaml
agents:
  runtime: claude_code   # 或 "codex"、"cursor"、"kiro"、"opencode"
  count: 3
  model: opus  

```

### 使用

```bash
# 启动
coral start -c examples/kernel_builder/task.yaml

# 通过 dotlist 语法覆盖任意配置
coral start -c task.yaml agents.count=4 agents.model=opus
coral start -c task.yaml run.verbose=true        # 流式输出 Agent 日志
coral start -c task.yaml run.ui=true             # 同时启动 Web 看板

# 停止和恢复
coral stop                                       # 暂停
coral resume                                     # 继续

# 监控进度
coral status                                     # CLI 排行榜
coral ui                                         # Web 看板
```

完整 CLI 参考见 [`coral --help`](https://human-agent-society.github.io/CORAL/cli/reference) 或运行 `coral --help`。配置项（warm-start、Gateway、Docker 会话等）详见[配置文档](https://human-agent-society.github.io/CORAL/getting-started/configuration)。

### 工作原理

<p align="center">
  <img src="assets/coral_diagram_trans.jpg" alt="CORAL Architecture Diagram" width="800">
</p>

每个 Agent 跑在自己的 git worktree 分支里。共享状态（历史记录、笔记、技能）放在 `.coral/public/`，软链到所有 worktree —— 零开销，实时互通。后台管理器盯着新提交，可以通过心跳机制打断 Agent 并注入指令（比如"回顾一下"、"整理技能"）。

| 概念 | 说明 |
|------|------|
| **Agent = 优化器** | Claude Code / Codex / OpenCode 子进程，各占一个 git worktree |
| **共享状态** | `.coral/` 存放历史记录、笔记和技能，软链到每个 worktree |
| **Eval 循环** | Agent 调 `coral eval -m "..."` 一步完成暂存 + 提交 + 打分 |
| **CLI 调度** | 17+ 条命令：`start`、`stop`、`status`、`eval`、`log`、`ui` 等 |
| **Web 看板** | `coral ui` —— 实时排行榜、diff 对比、Agent 监控 |

### 快速上手

三条命令即可启动：

```bash
coral init my-task                            # 生成 task.yaml + grader 模板 + seed/
# 编辑 my-task/task.yaml 和 my-task/eval/grader.py 描述你的问题
coral validate my-task                        # 用 seed/ 试跑一次评分器
coral start -c my-task/task.yaml              # 启动 Agent（自动开 tmux）
```

需要完整流程演示（含 seed 代码、grader、task.yaml、启动）以及 TSP 实战示例？参见[快速上手文档](https://human-agent-society.github.io/CORAL/getting-started/quickstart)。

### Agent 运行时与 Gateway

默认 Claude Code 无需额外配置（只需 Anthropic API key）。使用其他运行时请参考对应文档：

- [OpenCode](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#opencode) —— 需要在 seed 目录提供 `opencode.json`
- [Cursor Agent](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#cursor-agent) —— 执行 `cursor-agent login` 后设置 `runtime: cursor`
- [Kiro](https://human-agent-society.github.io/CORAL/guides/agent-runtimes#kiro) —— 安装并配置 `kiro-cli` 后设置 `runtime: kiro`

如需通过统一代理转发 Agent 流量（自定义模型、请求日志、按 Agent 隔离密钥），启用内置的 [LiteLLM Gateway](https://human-agent-society.github.io/CORAL/guides/gateway)。

### 示例

`examples/` 下有开箱即用的任务配置：

| 任务 | 领域 | 说明 |
|------|------|------|
| **circle_packing** | 优化 | 把 26 个圆塞进单位正方形，最大化半径总和 |
| **erdos** | 数学 | 求解数学猜想 |
| **kernel_builder** | 系统 | VLIW SIMD kernel 优化 |
| **kernel_engineering** | 系统 | GPU kernel 优化 |
| **mnist** | 机器学习 | 手写数字识别 |
| **spaceship_titanic** | 机器学习 | Kaggle 竞赛 |
| **stanford_covid_vaccine** | 生物/ML | mRNA 降解预测 |


### 开发

```bash
# 装开发依赖
uv sync --extra dev

# 跑测试
uv run pytest tests/ -v

# lint + 格式化
uv run ruff check .
uv run ruff format .
```

本项目在 Apache 2.0 [LICENSE](LICENSE) 许可下开源。

### 引用

⭐ 如果觉得 CORAL 对有帮助的话，欢迎给我们的 GitHub Repo 点个 Star。也可以考虑引用我们 (请使用下方的官方 BibTeX，而不要使用 Google Scholar 自动生成的引用，因为后者可能会截断作者列表)：

```bibtex
@article{qu2026coral,
  title={CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery},
  author={Qu, Ao and Zheng, Han and Zhou, Zijian and Yan, Yihao and Tang, Yihong and Ong, Shao Yong and Hong, Fenglu and Zhou, Kaichen and Jiang, Chonghe and Kong, Minwei and Zhu, Jiacheng and Jiang, Xuan and Li, Sirui and Wu, Cathy and Low, Bryan Kian Hsiang and Zhao, Jinhua and Liang, Paul Pu},
  journal={arXiv preprint arXiv:2604.01658},
  year={2026}
}
```

### 致谢

我们感谢 [TNT Accelerator](https://www.tnt.so/) 提供的慷慨支持，包括在开发过程中给予帮助的各种 API 积分。也要感谢许多如 [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)、[autoresearch](https://github.com/karpathy/autoresearch)、[TTT Discover](https://arxiv.org/abs/2601.16175) 等的十分有启发性的工作，这些工作为 Coral 的诞生奠定了基础。
