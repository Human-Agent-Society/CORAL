# 任务：CoFlyers Vasarhelyi 参数调优

## 任务概述

本任务要求 agent 在 `CoFlyers` 原仓公开发布的 `Vasarhelyi` 群飞 case 上进行参数调优。

每个 case 都提供一组原始 `baseline_params`。候选程序只能修改公开释放的 Vasarhelyi 可调参数，而不能改变控制器整体结构。

## 可调参数

- `r_rep_0`
- `p_rep`
- `r_frict_0`
- `c_frict`
- `v_frict`
- `p_frict`
- `a_frict`
- `r_shill_0`
- `v_shill`
- `p_shill`
- `a_shill`

## 背景与来源

`CoFlyers` 是一个面向无人机集群协同运动算法/模型评估与验证的平台。原始仓库中公开了：

- `Vasarhelyi` swarm module，
- `evaluation_0` evaluation module，
- 多组 `params_for_parallel` 参数样例。

本任务直接使用这些公开 case 参数作为 benchmark 输入来源，并在 Python 中重实现核心控制律与评估逻辑，以便统一接入 `Frontier-Engineering`。

## 输入定义

评测器会对每个 case 调用：

```python
solve(problem)
```

其中 `problem` 的结构为：

```python
{
  "case_id": str,
  "baseline_params": dict[str, float],
  "global_config": dict[str, Any],
}
```

含义如下：

- `case_id`：当前 CoFlyers case 的标识
- `baseline_params`：该 case 在原始发布参数中的基线参数
- `global_config`：从原仓配置抽取出的全局常量，例如群体规模、仿真时长、地图边界、点质量模型参数以及 `evaluation_0` 参数等

## 输出定义

候选程序必须返回字典。推荐格式为：

```python
{
  "params": {
    "r_rep_0": float,
    "p_rep": float,
    "r_frict_0": float,
    "c_frict": float,
    "v_frict": float,
    "p_frict": float,
    "a_frict": float,
    "r_shill_0": float,
    "v_shill": float,
    "p_shill": float,
    "a_shill": float,
  }
}
```

也允许直接返回参数更新字典。未显式提供的参数将沿用该 case 的 `baseline_params`。

## 评测流程

评测器对每个 case 执行以下步骤：

1. 根据抽取出的 CoFlyers 配置恢复初始机群布局和全局常量
2. 使用 Python 重实现的 `Vasarhelyi` 控制律生成期望速度
3. 使用点质量运动学更新群体状态
4. 计算与 CoFlyers `evaluation_0` 对齐的指标：
   - `phi_corr`
   - `phi_vel`
   - `phi_coll`
   - `phi_wall`
   - `phi_mnd`
5. 汇总单个 case 的结果，并在所有公开 case 上求平均，得到 `combined_score`

## 评分指标

评测器会输出：

- `combined_score`：主 benchmark 分数，越高越好
- `mean_original_fitness`：按 CoFlyers 原始 fitness 形式统计的平均值
- `mean_phi_corr`：平均速度方向一致性
- `mean_phi_vel`：平均速度相对于 flocking 目标速度的比值
- `mean_phi_coll`：平均碰撞占比
- `mean_phi_wall`：平均贴墙 / 越界占比
- `mean_phi_mnd`：平均最小邻距惩罚项
- `worst_min_pairwise_distance`：所有 case 中最差的最小机间距

## 约束

- 只能调节公开释放的 `Vasarhelyi` 参数集合
- 不得修改评测器、原始 case 数据或 `frontier_eval` 元数据
- 候选程序必须保持可执行、确定性和输出格式兼容

## 说明

本任务忠实使用了 CoFlyers 原仓公开发布的 case 参数，但执行后端是 **Python 重实现**，而不是直接调用原始 MATLAB/Simulink 运行时。


