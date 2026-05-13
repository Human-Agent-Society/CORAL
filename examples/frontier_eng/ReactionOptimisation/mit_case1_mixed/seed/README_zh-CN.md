# MIT Case 1 Mixed

这个任务来自 SUMMIT 的 `MIT_case1` benchmark。它是一个很紧凑的混合变量优化问题：三个连续工艺变量，加上一个离散催化剂选择。

如果你想练习“离散决策 + 连续调参”同时存在、而且实验预算很小的黑盒优化任务，这个目录很适合。

当前实现方法：

- `baseline/solution.py`：混合随机 + 局部搜索。它主要在“随机探索”和“围绕当前最好收率点做局部扰动”之间切换，不调用外部现成优化器。
- `verification/reference.py`：直接在混合变量域上跑 SUMMIT `SOBO`。离散催化剂变量仍然放在 SUMMIT 的 domain 中，由 `SOBO` 完整处理逐步建议实验的过程。

当前目录结构：

- `task.py`：benchmark 构造、变量范围、扰动工具和评分定义
- `Task.md`：英文版完整任务说明
- `Task_zh-CN.md`：中文版完整任务说明
- `baseline/solution.py`：简单的混合随机 / 局部搜索基线
- `verification/reference.py`：基于 SUMMIT 的参考优化器
- `verification/evaluate.py`：统一运行和评分
