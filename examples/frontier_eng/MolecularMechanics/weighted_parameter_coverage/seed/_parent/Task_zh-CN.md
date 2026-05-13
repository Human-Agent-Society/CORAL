# OpenFF Optimization Tasks

这个目录把任务拆成两层：

- 算法层
  - `baseline/init.py`
  - 尽量不依赖 OpenFF / RDKit / OpenMM
  - 只负责做核心优化
- 化学评测层
  - `verification/evaluate.py`
  - 负责把原始化学输入转换成算法输入
  - 负责调用外部库进行真实评测

## 参考值术语

这几个任务里会出现三类不同的“参考值”：

- `真最优`
  - 对当前这个具体实例，确实把优化问题精确求解出来
- `可证上界`
  - 不一定能达到，但可以证明任何合法解都不会超过它
- `已知最优`
  - 不是评测时重新求出来的，而是 benchmark 设计时就已知的最优分数

三道任务分别使用：

- `weighted_parameter_coverage`
  - 用整数规划精确求解，所以 `exact_optimal_score` 和 `certified_upper_bound` 相同
- `diverse_conformer_portfolio`
  - 不求真最优，只构造严格成立但可能偏松的 `certified_upper_bound`
- `torsion_profile_fitting`
  - 使用任务定义中写明的 `known_optimal_score`

## 当前 starter 水平

在 `2026-03-16` 的当前配置下，三个 `baseline/init.py` 的差距是：

- `weighted_parameter_coverage`
  - 距离真最优 `63.067%`
- `diverse_conformer_portfolio`
  - 距离可证上界 `58.777%`
- `torsion_profile_fitting`
  - 距离已知最优 `65.256%`

所以这三道题现在都不是“小范围调一调就见顶”的演示题，而是留出了比较明确的优化空间。

## 目录

- [weighted_parameter_coverage](weighted_parameter_coverage/)
  - 带预算约束的加权覆盖优化
- [diverse_conformer_portfolio](diverse_conformer_portfolio/)
  - 低能量且多样化的构象组合优化
- [torsion_profile_fitting](torsion_profile_fitting/)
  - 连续参数下的扭转能量曲线拟合

## 推荐阅读顺序

如果你是第一次看，建议按这个顺序：

1. 先看 [README_zh-CN.md](README_zh-CN.md)
   - 了解文件结构、环境配置和通用运行方式
2. 再看某个任务目录下的 `Task_zh-CN.md`
   - 了解任务背景、输入输出和打分方式
3. 最后看 `baseline/init.py`
   - 看当前 starter 是怎么实现的
