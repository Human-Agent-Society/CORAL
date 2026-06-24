
<div align="center">

<img src="assets/logo.png" alt="CORAL logo —— 多 Agent 自主编程基础设施" width="360">

## **一键启动智能体群组，共享知识，无限进化**

<p>
  <img src="assets/mit_logo.png" alt="MIT" height="50">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/nus.png" alt="NUS" height="50">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/stanford.png" alt="Stanford" height="50">
</p>

[![Paper](https://img.shields.io/badge/Paper-arXiv%3A2604.01658-B31B1B.svg?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2604.01658v1)
[![Blog](https://img.shields.io/badge/Blog-CORAL-FF6B6B.svg?logo=hashnode&logoColor=white)](https://human-agent-society.github.io/CORAL/)
[![Apache 2.0 License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)

[English](README.md) | **中文**

</div>

<p align="center">
<a href="#安装">安装</a> · <a href="#插件在你自己的-agent-里使用-coral">插件</a> · <a href="#支持的-agent">支持的 Agent</a> · <a href="#工作原理">工作原理</a> · <a href="#示例">示例</a> · <a href="https://docs.coralxyz.com/">文档</a> · <a href="https://arxiv.org/abs/2604.01658v1">论文</a>
</p>

**CORAL** 是用于构建**自主 AI Agent 组织**的基础设施 —— Agent 持续运行实验、共享知识、不断进化。只需提供代码库和评分脚本，CORAL 负责其余的一切：隔离工作空间、安全评估、持久共享状态、多 Agent 协作。原生集成 Claude Code、OpenCode、Codex、Cursor Agent、Kiro。

### 🔥 News

- **[2026-06-24]** Docker 会话支持隔离 agent 与 grader：设置 `agents.isolate_user=agent` 即可让每个 agent 以非特权用户运行（manager 与 grader 仍为 root），agent 将无法读取 `.coral/private/`（grader 虚拟环境、答案 key）—— 即使通过 Bash 也不行。
- **[2026-06-13]** 旧版 `eval/grader.py` grader 自动发现已废弃并移除 —— 改用 `grader.entrypoint` 指向打包的 grader。详见 [自定义 Grader 文档](https://docs.coralxyz.com/guides/custom-grader)。
- **[2026-04-24]** 新增 Rubric 评审 —— 两个开箱即用的 LLM 评审 grader 包，专为开放式任务（报告、备忘、法律分析）设计。详见 [Rubric Judges 文档](https://docs.coralxyz.com/guides/rubric-judge)。
- **[2026-04-03]** 我们的论文 "CORAL: Towards Autonomous Multi-Agent Evolution for Open-Ended Discovery" 现已发布！请查看 [Arxiv](https://arxiv.org/abs/2604.01658v1)。
- **[2026-03-18]** CORAL 正式发布！点击查看 [Blog](https://human-agent-society.github.io/CORAL/)。

![CORAL 多 Agent 自主编程演示 —— 多个编程 Agent 在独立 git worktree 中并行运行,通过共享状态目录交换知识](assets/demo.gif)

### 安装

```bash
curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh
```

通过 `uv tool install` 全局安装**最新版 `coral`**。如确需指定版本，设置 `CORAL_VERSION=<tag>`。手动安装、开发模式、前置依赖等详见[安装文档](https://docs.coralxyz.com/getting-started/installation)。

```bash
coral init my-task                       # 生成任务模板
cd my-task && coral start -c task.yaml   # 启动 Agent
```

### 插件：在你自己的 Agent 里使用 CORAL

想在**你自己的** Claude Code 或 Codex 里编写、运行 CORAL 任务，又不想记 CLI？安装 CORAL 插件——一个以 skill 为主的包（不含 MCP），教会 Agent 整套流程（`coral setup` → `init`/`validate` → `start`/`status`/`log`），并在会话开始时检查 `coral` 是否已安装。

**Claude Code：**

```
/plugin marketplace add Human-Agent-Society/CORAL
/plugin install coral@coral-marketplace
```

**Codex**（v0.117.0+）：

```
codex plugin marketplace add Human-Agent-Society/CORAL
codex plugin add coral@coral-marketplace
```

两者都从本仓库的 marketplace 清单拉取；插件位于 [`plugin/`](plugin/)。

**快速上手——让 CORAL 优化你已有的代码。** 装好后，打开你想优化的代码仓库，直接说一句：

```
用 coral 优化这个 —— 在不改变输出的前提下让 saga/decode.py 里的 sample() 更快
```

插件会自动开一个被 gitignore 的 `.coral_workspace/`，把你的代码放进 `seed/`，按你的指标写好 grader，并反复跑 `coral validate` 直到任务可启动——最后把 `coral start` 命令交给你。在 Claude Code 上，`coral-task-author` 子 agent 会自主完成整个搭建过程（另有 `coral-run-doctor` 负责诊断卡住的 run）；在其他 harness 上，打包的 skill 会带你走同样的流程。

包含的 skill：`coral-quickstart`（安装 → setup → `.coral_workspace/`）、`setting-up-coral`（运行时绑定）、`creating-a-coral-task`（编写 grader）、`running-coral-experiments`（运维一个 run）。子 agent、skill 目录手动安装方式及其他 harness，见[插件指南](https://docs.coralxyz.com/guides/plugin)或 [`plugin/README.md`](plugin/README.md)。

### 支持的 Agent

| Agent | `agents.runtime` |
|-------|------------------|
| [Claude Code](https://github.com/anthropics/claude-code) —— 默认 | `claude_code` |
| [Codex](https://github.com/openai/codex) | `codex` |
| [Cursor Agent](https://cursor.com/docs/cli/overview) | `cursor` |
| [Kiro](https://kiro.dev) | `kiro` |
| [OpenCode](https://github.com/opencode-ai/opencode) | `opencode` |

每个 Agent 需自行安装并完成认证。各运行时的详细配置（含[ LiteLLM Gateway](https://docs.coralxyz.com/guides/gateway) 自定义模型代理）见 [Agent 运行时文档](https://docs.coralxyz.com/guides/agent-runtimes)。

### 工作原理

<p align="center">
  <img src="assets/coral_diagram_trans.jpg" alt="CORAL 架构图:多个编程 Agent 运行在隔离的 git worktree 中,通过 .coral/public/ 共享状态,由 grader 守护进程评分" width="800">
</p>

每个 Agent 跑在自己的 git worktree 里。共享状态（历史记录、笔记、技能）放在 `.coral/public/`，软链到所有 worktree —— Agent 实时看到彼此的工作。Grader 守护进程为每次提交打分。后台管理器通过心跳机制打断 Agent 并注入指令（`reflect`、`consolidate`、`pivot`）。

深入阅读：[核心概念](https://docs.coralxyz.com/concepts) · [多 Agent 运行](https://docs.coralxyz.com/guides/multi-agent) · [评估循环](https://docs.coralxyz.com/concepts/eval-loop)

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

完整任务清单与详解见[示例文档](https://docs.coralxyz.com/examples)。

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

### 参与贡献

欢迎社区贡献 —— bug 报告、`examples/` 下的新任务、新的 agent runtime、文档改进，都很欢迎。先看这里：

- [CONTRIBUTING.md](CONTRIBUTING.md) —— 开发环境、分支与 commit 规范、PR 流程、测试与 lint 命令。
- [AGENTS.md](AGENTS.md) —— AI 辅助贡献的规则（CORAL 本身就是 agent 基础设施，所以我们对 agent 写的 PR 有一些具体要求）。

想深入了解代码结构，可以读 [CLAUDE.md](CLAUDE.md) 里的架构说明 —— 覆盖 eval loop、`.coral/{public,private}/` 划分、grader daemon、runtime registry。

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
