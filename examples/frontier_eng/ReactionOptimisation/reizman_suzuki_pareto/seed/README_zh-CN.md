# Reizman Suzuki Pareto

这个任务来自 SUMMIT 的 Suzuki 偶联预训练仿真器。它同时包含离散催化剂选择和连续工艺条件，并且是双目标优化。

如果你想做一个更像工程开发流程的 Pareto 优化任务，而且类别选择会极大影响结果，这个目录很合适。

当前实现方法：

- `baseline/solution.py`：纯随机搜索。每一步都重新随机采样催化剂和连续工艺条件，所以它更像一个简单下限。
- `verification/reference.py`：两阶段 SUMMIT 搜索。先在固定筛选条件下把所有催化剂都评估一遍，再针对更有希望的催化剂 / 标量化权重组合，在固定催化剂的三维连续子空间里跑 `SOBO`。

当前目录结构：

- `task.py`：benchmark 构造、变量范围、标量化辅助函数和评分定义
- `Task.md`：英文版完整任务说明
- `Task_zh-CN.md`：中文版完整任务说明
- `baseline/solution.py`：简单的纯随机基线
- `verification/reference.py`：先筛选催化剂、再做固定催化剂 SUMMIT 优化的参考解
- `verification/evaluate.py`：统一运行并报告分数差距
