# DTLZ2 Pareto

这个任务包装的是 SUMMIT 的 `DTLZ2` benchmark。它是一个合成多目标问题，并且已知理论 Pareto 前沿。

它没有前几个任务那么“化工”，但非常适合调试和验证优化代码，因为它的分数存在精确理论上限。

当前实现方法：

- `baseline/solution.py`：随机标量化 + 局部扰动。它会在几个标量化权重之间轮换，维护一个当前标量化最优点，并围绕这个点做连续变量搜索。
- `verification/reference.py`：拆分预算的 SUMMIT 标量化贝叶斯优化。它会对多个权重分别运行 `SOBO`，再把得到的点合并后统一评分。

当前目录结构：

- `task.py`：benchmark 构造、候选点工具和精确评分定义
- `Task.md`：英文版完整任务说明
- `Task_zh-CN.md`：中文版完整任务说明
- `baseline/solution.py`：简单的连续随机搜索基线
- `verification/reference.py`：基于 SUMMIT 标量化搜索的参考解
- `verification/evaluate.py`：同时对比 baseline、reference 和理论上限
