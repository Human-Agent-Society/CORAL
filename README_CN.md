<div align="center">

<img src="assets/coral_logo_transparent.jpg" alt="CORAL" width="360">

### **启动智能体，共享知识，永不停歇地优化。**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-5C4EE5.svg)](https://docs.astral.sh/uv/)

[English](README.md) | **中文**

一个**自主智能体**组织 ——
运行实验、共享知识、循环迭代，直到收敛到最优解。

</div>

<p align="center">
<a href="#安装">安装</a> · <a href="#使用方式">使用方式</a> · <a href="#工作原理">工作原理</a> · <a href="#核心概念">核心概念</a> · <a href="#快速开始">快速开始</a> · <a href="#cli-命令参考">CLI 命令</a> · <a href="#示例">示例</a> · <a href="#许可证">许可证</a>
</p>

## 安装

```bash
git clone https://github.com/Human-Agent-Society/CORAL.git
cd CORAL
uv sync
```

## 使用方式

### 🚀 一份配置，N 个智能体，持续刷新 SOTA。

```bash
uv run coral start --config task.yaml
```

### ⏹️ 随时暂停，随时恢复。

```bash
uv run coral stop                                      # 随时停止
uv run coral resume                                    # 从中断处继续
```

### 📊 一键可视化。

```bash
uv run coral ui                                        # 打开 Web 仪表盘
```

## 工作原理

```mermaid
graph TD
    subgraph Setup["coral start"]
        A[创建 .coral/ 共享状态] --> B[克隆仓库 + 创建 per-agent worktree]
        B --> C[将 .coral/public/ 符号链接到每个 worktree]
        C --> D[为每个智能体生成 CORAL.md]
        D --> E[启动 N 个智能体]
    end

    subgraph Loop["每个智能体（自主运行）"]
        F[读取 CORAL.md + 排行榜 + 笔记 + 技能] --> G[规划 & 编辑代码]
        G --> H["coral eval -m '描述'"]
        H --> I["git add → commit → 评分 → 写入 attempt"]
        I --> J[将笔记与技能写入 .coral/public/]
        J --> F
    end

    subgraph Monitor["管理器（后台）"]
        K[监听 .coral/public/attempts/] --> L{触发心跳动作？}
        L -->|是| M[中断 + 恢复智能体并附带提示]
        L -->|否| K
    end

    E --> Loop
    E --> Monitor

    style Setup fill:#f0fdfa,stroke:#0d9488
    style Loop fill:#fffbeb,stroke:#f59e0b
    style Monitor fill:#f5f3ff,stroke:#8b5cf6
```

每个智能体运行在独立的 git worktree 分支中。共享状态（尝试记录、笔记、技能）存放在 `.coral/public/`，通过符号链接同步到每个 worktree —— 零同步开销，实时可见。管理器在后台监听新的尝试记录，并可通过心跳机制中断智能体注入提示（如"反思"、"整理技能"）。

## 核心概念

| 概念 | 说明 |
|------|------|
| **智能体即优化器** | Claude Code / Codex / OpenCode 子进程，各自运行在独立的 git worktree 中 |
| **共享状态** | `.coral/` 目录包含尝试记录、笔记和技能 —— 通过符号链接同步到每个 worktree |
| **评估循环** | 智能体调用 `uv run coral eval -m "..."` 一步完成暂存、提交和评分 |
| **CLI 编排** | 17+ 个命令：`start`、`stop`、`status`、`eval`、`log`、`ui` 等 |
| **Web 仪表盘** | `uv run coral ui` —— 实时排行榜、尝试记录对比、智能体监控 |

## 快速开始

### 1. 创建任务

```yaml
# my-task/task.yaml
task:
  name: my-task
  description: "优化 solution.py 中的函数"

grader:
  type: function
  module: eval.grader

agents:
  count: 2
  model: claude-sonnet-4-20250514
  max_turns: 200
```

### 2. 编写评分器

```python
# my-task/eval/grader.py
from coral.grader import TaskGrader

class Grader(TaskGrader):
    def evaluate(self) -> float:
        result = self.run_program("solution.py")
        return float(result.stdout.strip())
```

### 3. 启动

```bash
uv run coral start --config my-task/task.yaml
uv run coral ui          # 打开 Web 仪表盘
uv run coral status      # CLI 排行榜
uv run coral log         # 查看尝试记录
uv run coral stop        # 停止所有智能体
```

## CLI 命令参考

<details>
<summary>点击展开全部 17+ 个命令</summary>

| 命令 | 说明 |
|------|------|
| `uv run coral init <name>` | 初始化新任务 |
| `uv run coral validate <name>` | 测试评分器 |
| `uv run coral start -c task.yaml` | 启动智能体 |
| `uv run coral resume` | 恢复之前的运行 |
| `uv run coral stop` | 停止所有智能体 |
| `uv run coral status` | 智能体状态 + 排行榜 |
| `uv run coral log` | 排行榜（前 20） |
| `uv run coral log -n 5 --recent` | 最近的尝试记录 |
| `uv run coral log --search "关键词"` | 搜索尝试记录 |
| `uv run coral show <hash>` | 尝试详情 + diff |
| `uv run coral notes` | 浏览共享笔记 |
| `uv run coral skills` | 浏览共享技能 |
| `uv run coral runs` | 列出所有运行 |
| `uv run coral ui` | Web 仪表盘 |
| `uv run coral eval -m "描述"` | 暂存、提交、评估（智能体调用） |
| `uv run coral diff` | 查看未提交的变更 |
| `uv run coral revert` | 撤销上次提交 |
| `uv run coral checkout <hash>` | 重置到之前的尝试 |
| `uv run coral heartbeat` | 查看/修改心跳动作 |

</details>

## 评分系统

<details>
<summary>点击展开</summary>

评分器实现 `GraderInterface` 协议：

```python
class GraderInterface(Protocol):
    async def grade(self, codebase_path: str, tasks: list[Task], **kwargs) -> ScoreBundle: ...
```

内置评分器：

| 评分器 | 用途 |
|--------|------|
| **TaskGrader** | 任务评分器基类 —— 提供 `run_program`、`read_eval`、`score`、`fail` 等辅助方法 |
| **FunctionGrader** | 将任意 `(codebase_path, tasks) -> Score | float | bool` 可调用对象封装为评分器 |

</details>

## 项目结构

<details>
<summary>点击展开</summary>

```
coral/
├── types.py             # Task, Score, ScoreBundle, Attempt
├── config.py            # 基于 YAML 的 CoralConfig
├── agent/
│   ├── manager.py       # 多智能体生命周期管理
│   └── runtime.py       # Claude Code / Codex / OpenCode 子进程
├── workspace/
│   └── setup.py         # Worktree 创建、钩子、符号链接
├── grader/
│   ├── protocol.py      # GraderInterface 协议
│   ├── base.py          # BaseGrader（辅助方法：_make_score, _make_bundle）
│   ├── task_grader.py   # TaskGrader 任务评分器基类
│   ├── loader.py        # 评分器发现与加载
│   └── builtin/
│       └── function_grader.py
├── hub/
│   ├── attempts.py      # 尝试记录 CRUD + 排行榜 + 搜索
│   ├── notes.py         # Markdown 笔记（YAML frontmatter）
│   └── skills.py        # 技能目录（含 SKILL.md）
├── hooks/
│   └── post_commit.py   # 提交后评估实现
├── template/
│   └── coral_md.py      # CORAL.md 生成器
├── web/                 # Starlette + React 仪表盘
└── cli/                 # 5 个模块，17 个命令
```

</details>

## 示例

`examples/` 目录中包含可直接运行的任务配置：

| 任务 | 领域 | 说明 |
|------|------|------|
| **circle_packing** | 优化 | 将 26 个圆填入单位正方形，最大化半径之和 |
| **erdos** | 数学 | 求解数学猜想 |
| **kernel_builder** | 系统 | VLIW SIMD 内核优化 |
| **kernel_engineering** | 系统 | GPU 内核优化 |
| **mnist** | 机器学习 | 手写数字分类 |
| **spaceship_titanic** | 机器学习 | Kaggle 竞赛 |
| **stanford_covid_vaccine** | 生物/ML | mRNA 降解预测 |

## 开发

<details>
<summary>点击展开</summary>

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 构建 | Hatchling |
| 包管理 | uv |
| Web 后端 | Starlette |
| Web 前端 | React + TypeScript (Vite) |
| 核心依赖 | PyYAML |
| 可选依赖 | swebench, datasets, docker, harbor |

```bash
# 安装开发依赖
uv sync --extra dev

# 运行测试
uv run pytest tests/ -v

# 代码检查与格式化
uv run ruff check .
uv run ruff format .
```

</details>

## 许可证

MIT —— 详见 [LICENSE](LICENSE)。
