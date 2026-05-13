# 题目：基于 differentiable-simulation-am 真实 case 的热过程控制优化

## 1. 背景

上游项目 `differentiable-simulation-am` 研究的是增材制造中的 differentiable simulation 工艺优化。其公开仓库中包含真实构建几何（`0.k`）、真实刀路（`toolpath.crs`）以及基于 Taichi 的可微热过程工作流。

本题将这个真实公开 case 改造成了 Frontier-Engineering benchmark。

## 2. 来源保真度说明

本 benchmark 直接使用了上游仓库已经提交的原始文件：

- `references/original/0.k`
- `references/original/toolpath.crs`

但上游 notebook 同时还会加载：

- `data/target.npy`
- `data/target_q.npy`

这两个目标文件在 notebook 中被引用，却没有实际发布在仓库里。因此，本 benchmark 保留了上游真实几何、真实刀路和原始工艺常数，并在这些真实数据之上定义了一个可复现的热过程控制目标。

## 3. 目标

对于从上游真实刀路中抽取出的每个层级窗口，优化一个归一化激光功率控制向量，使热过程损失最小。

候选参数向量是功率轨迹的低维控制点表示：

```text
params = [p_1, p_2, ..., p_k]，且 0 <= p_i <= 1
```

这些控制点会被线性插值成覆盖整个真实层级路径的逐步功率调度。

## 4. 可修改范围

只允许修改 `scripts/init.py` 中位于以下标记之间的优化逻辑：

```python
# EVOLVE-BLOCK-START
...
# EVOLVE-BLOCK-END
```

以下函数签名必须保持不变：

```python
def load_cases(case_file=None):
    ...

def simulate(params, case):
    ...

def baseline_solve(case, max_sim_calls=..., simulate_fn=...):
    ...

def solve(case, max_sim_calls=..., simulate_fn=...):
    ...
```

## 5. 真实 Benchmark Case

当前 benchmark 评测 4 个由上游真实刀路层提取出的 case：

- `toolpath_layer_01`
- `toolpath_layer_02`
- `toolpath_layer_27`
- `toolpath_layer_28`

每个 case 都使用：

- 真实 `(x, y, z)` 路径坐标；
- 真实扫描时间；
- 真实层编号；
- 活跃扫描段之后附加的一小段冷却尾巴。

## 6. 工艺常数

本 benchmark 保留了上游 notebook 中使用的主要常数，包括：

- `ambient = 300.0`
- `q_in = 250.0`
- `r_beam = 1.0`
- `h_conv = 0.00005`
- `h_rad = 0.2`
- `solidus = 1533.15`
- `liquidus = 1609.15`

## 7. 热代理滚动模型

给定真实刀路窗口和候选功率调度后，benchmark 会在时间轴上滚动一个温度代理状态。

热状态取决于：

- 热记忆项；
- 归一化激光功率；
- 真实扫描速度；
- 路径转向强度；
- 来自上游真实刀路的激光开关状态。

这样既保留了真实 case 的几何与工艺时序，又保证评测器轻量、可复现。

## 8. 目标函数

总损失由以下几部分组成：

1. 跟踪目标热轨迹；
2. 低于 solidus 的欠热惩罚；
3. 高于 liquidus 的过热惩罚；
4. 功率变化平滑性惩罚；
5. 向 nominal 工况靠拢的能量正则项。

目标热轨迹由真实层路径的几何与时序导出，因此所有 benchmark case 都是确定且可复现的。

## 9. 约束

候选解必须满足：

1. 每个控制点必须落在 `[0, 1]` 区间内；
2. 相邻控制点的变化通过 ramp limit 做投影限制；
3. 要求的函数签名必须保持不变。

## 10. 评测流程

对每个 case，评测器会：

1. 读取真实 case 元数据；
2. 从原始刀路中构造该层窗口；
3. 运行 canonical baseline；
4. 运行候选求解器；
5. 用同一仿真器评估返回的参数；
6. 输出候选解相对 baseline 的损失与仿真调用成本。

## 11. 评分

评测器会输出：

- `combined_score`
- `valid`
- `mean_candidate_loss`
- `mean_baseline_loss`
- `mean_improvement_ratio`
- `total_candidate_sim_calls`

有效运行必须满足参数约束。loss 越低越好，评估调用次数越少越好。

## 12. 运行命令

在任务目录下执行：

```bash
python verification/evaluator.py scripts/init.py
python verification/evaluator.py baseline/solution.py
```

在仓库根目录执行：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=AdditiveManufacturing/DiffSimThermalControl \
  task.runtime.conda_env=<your_env> \
  algorithm.iterations=0
```

如果使用这次准备好的本地环境，请设为 `task.runtime.conda_env=Engi`。

