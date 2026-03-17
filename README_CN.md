<div align="center">

<img src="assets/coral_logo_transparent.png" alt="CORAL" width="360">

### **放出 Agent。共享知识。永远进化。**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-5C4EE5.svg)](https://docs.astral.sh/uv/)

[English](README.md) | **中文**

一群**自主 AI Agent** ——
不断试验、互通有无、持续进化，把答案越磨越好。

</div>

<p align="center">
<a href="#安装">安装</a> · <a href="#使用">使用</a> · <a href="#工作原理">工作原理</a> · <a href="#核心概念">核心概念</a> · <a href="#快速上手">快速上手</a> · <a href="#cli-命令">CLI 命令</a> · <a href="#示例">示例</a> · <a href="#许可证">许可证</a>
</p>

## 安装

```bash
git clone https://github.com/Human-Agent-Society/CORAL.git
cd CORAL
uv sync
```

## 使用

### 🚀 一份配置，N 个 Agent，冲击 SOTA。

```bash
uv run coral start --config task.yaml
```

### ⏹️ 随时停，随时续。

```bash
uv run coral stop                                      # 停
uv run coral resume                                    # 续
```

### 📊 可视化看板，开箱即用。

```bash
uv run coral ui                                        # 打开 Web 看板
```

## 工作原理

```mermaid
graph TD
    subgraph Setup["coral start"]
        A[创建 .coral/ 共享状态] --> B[克隆仓库 + 为每个 Agent 开 worktree]
        B --> C[把 .coral/public/ 软链到各 worktree]
        C --> D[给每个 Agent 生成 CORAL.md]
        D --> E[拉起 N 个 Agent]
    end

    subgraph Loop["每个 Agent（自主循环）"]
        F[读 CORAL.md + 排行榜 + 笔记 + 技能] --> G[思考 & 改代码]
        G --> H["coral eval -m '描述'"]
        H --> I["git add → commit → 打分 → 记录"]
        I --> J[把笔记和技能写入 .coral/public/]
        J --> F
    end

    subgraph Monitor["管理器（后台）"]
        K[监听 .coral/public/attempts/] --> L{需要心跳干预？}
        L -->|是| M[打断 Agent 并注入提示]
        L -->|否| K
    end

    E --> Loop
    E --> Monitor

    style Setup fill:#f0fdfa,stroke:#0d9488
    style Loop fill:#fffbeb,stroke:#f59e0b
    style Monitor fill:#f5f3ff,stroke:#8b5cf6
```

每个 Agent 跑在自己的 git worktree 分支里。共享状态（历史记录、笔记、技能）放在 `.coral/public/`，软链到所有 worktree —— 零开销，实时互通。后台管理器盯着新提交，可以通过心跳机制打断 Agent 并注入指令（比如"回顾一下"、"整理技能"）。

## 核心概念

| 概念 | 说明 |
|------|------|
| **Agent = 优化器** | Claude Code / Codex / OpenCode 子进程，各占一个 git worktree |
| **共享状态** | `.coral/` 存放历史记录、笔记和技能，软链到每个 worktree |
| **Eval 循环** | Agent 调 `uv run coral eval -m "..."` 一步完成暂存 + 提交 + 打分 |
| **CLI 调度** | 17+ 条命令：`start`、`stop`、`status`、`eval`、`log`、`ui` 等 |
| **Web 看板** | `uv run coral ui` —— 实时排行榜、diff 对比、Agent 监控 |

## 快速上手

### 1. 定义任务

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

### 2. 写评分器

```python
# my-task/eval/grader.py
from coral.grader import TaskGrader

class Grader(TaskGrader):
    def evaluate(self) -> float:
        result = self.run_program("solution.py")
        return float(result.stdout.strip())
```

### 3. 跑起来

```bash
uv run coral start --config my-task/task.yaml
uv run coral ui          # 打开 Web 看板
uv run coral status      # 看排行榜
uv run coral log         # 翻记录
uv run coral stop        # 收工
```

## CLI 命令

<details>
<summary>展开全部 17+ 条命令</summary>

| 命令 | 说明 |
|------|------|
| `uv run coral init <name>` | 新建任务脚手架 |
| `uv run coral validate <name>` | 测试评分器 |
| `uv run coral start -c task.yaml` | 启动 Agent |
| `uv run coral resume` | 恢复上次运行 |
| `uv run coral stop` | 停止全部 Agent |
| `uv run coral status` | Agent 状态 + 排行榜 |
| `uv run coral log` | 排行榜（前 20） |
| `uv run coral log -n 5 --recent` | 最近的记录 |
| `uv run coral log --search "关键词"` | 搜索记录 |
| `uv run coral show <hash>` | 记录详情 + diff |
| `uv run coral notes` | 浏览笔记 |
| `uv run coral skills` | 浏览技能 |
| `uv run coral runs` | 列出所有运行 |
| `uv run coral ui` | Web 看板 |
| `uv run coral eval -m "描述"` | 暂存 + 提交 + 评估 |
| `uv run coral diff` | 看未提交的改动 |
| `uv run coral revert` | 撤销上次提交 |
| `uv run coral checkout <hash>` | 回退到指定记录 |
| `uv run coral heartbeat` | 查看/修改心跳动作 |

</details>

## 评分系统

<details>
<summary>展开</summary>

评分器需实现 `GraderInterface` 协议：

```python
class GraderInterface(Protocol):
    async def grade(self, codebase_path: str, tasks: list[Task], **kwargs) -> ScoreBundle: ...
```

内置评分器：

| 评分器 | 用途 |
|--------|------|
| **TaskGrader** | 任务评分基类 —— 提供 `run_program`、`read_eval`、`score`、`fail` 等工具方法 |
| **FunctionGrader** | 把任意 `(codebase_path, tasks) -> Score | float | bool` 函数包成评分器 |

</details>

## 项目结构

<details>
<summary>展开</summary>

```
coral/
├── types.py             # Task, Score, ScoreBundle, Attempt
├── config.py            # YAML 配置加载
├── agent/
│   ├── manager.py       # 多 Agent 生命周期
│   └── runtime.py       # Claude Code / Codex / OpenCode 子进程
├── workspace/
│   └── setup.py         # Worktree 创建、hook、软链
├── grader/
│   ├── protocol.py      # GraderInterface 协议
│   ├── base.py          # BaseGrader（_make_score, _make_bundle）
│   ├── task_grader.py   # TaskGrader 任务评分基类
│   ├── loader.py        # 评分器发现与加载
│   └── builtin/
│       └── function_grader.py
├── hub/
│   ├── attempts.py      # 记录增删改查 + 排行榜 + 搜索
│   ├── notes.py         # Markdown 笔记（YAML frontmatter）
│   └── skills.py        # 技能包（含 SKILL.md）
├── hooks/
│   └── post_commit.py   # 提交后自动评估
├── template/
│   └── coral_md.py      # CORAL.md 生成器
├── web/                 # Starlette + React 看板
└── cli/                 # 5 个模块，17 条命令
```

</details>

## 示例

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

## 开发

<details>
<summary>展开</summary>

| 组件 | 技术栈 |
|------|--------|
| 语言 | Python 3.11+ |
| 构建 | Hatchling |
| 包管理 | uv |
| Web 后端 | Starlette |
| Web 前端 | React + TypeScript (Vite) |
| 核心依赖 | PyYAML |
| 可选依赖 | swebench, datasets, docker, harbor |

```bash
# 装开发依赖
uv sync --extra dev

# 跑测试
uv run pytest tests/ -v

# lint + 格式化
uv run ruff check .
uv run ruff format .
```

</details>

## 许可证

MIT —— 详见 [LICENSE](LICENSE)。
