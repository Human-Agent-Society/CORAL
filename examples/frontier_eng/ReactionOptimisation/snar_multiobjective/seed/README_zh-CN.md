# SnAr Multiobjective

这个任务来自 SUMMIT 的 `SnarBenchmark`，背景是连续流反应优化：我们既想要高产能，也不希望产生太多废物。

如果你想练习一个更贴近工程实际、预算很小、而且是双目标权衡的黑盒优化问题，就可以从这个目录开始。

当前实现方法：

- `baseline/solution.py`：自适应随机标量化搜索。它会在几个目标权重之间轮换，每一步要么随机采样，要么围绕当前标量化最优点做扰动，用一个很简单的代理方式去逼近 Pareto 集。
- `verification/reference.py`：加权 SUMMIT 贝叶斯优化。它会先把预算拆给多个标量化权重，然后对每个权重分别调用 `SOBO` + `MultitoSingleObjective`，最后把所有观测点合并成一个 Pareto 候选集。

当前目录结构：

- `task.py`：变量范围、benchmark 构造、标量化辅助函数和评分定义
- `Task.md`：英文版完整任务说明
- `Task_zh-CN.md`：中文版完整任务说明
- `baseline/solution.py`：简单的自适应随机搜索
- `verification/reference.py`：基于 SUMMIT 的参考搜索方法
- `verification/evaluate.py`：对 baseline 和 reference 做统一评测
