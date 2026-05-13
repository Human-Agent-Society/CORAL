# 相位 DOE P3 说明：Dammann 均匀级次

## 背景
这是一个**参数优化问题**。
你要优化一维向量 `transitions`（单周期内二值相位切换位置），并通过仿真器评估结果。

可视为：
- 决策变量：`transitions`（连续向量）
- 仿真器：`diffractio` 传播流程
- 目标：让指定衍射级次更均匀且效率更高

## 你要做什么
改进 baseline 的跃迁位置生成策略。

主要优化点：
- `baseline_transitions(problem)`

`solve_baseline(problem)` 会调用它，然后构场、传播、评估指标。

## 可修改边界
- 可修改：`baseline/init.py`
- 只读：`verification/validate.py`

评测依赖接口：
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> dict`
- `build_incident_field(problem: dict, transitions: np.ndarray)`
- `evaluate_orders(problem: dict, intensity_x: np.ndarray, x: np.ndarray) -> dict`


### 输入
`problem` 包含：
- 周期、波长、焦距、采样参数
- 目标衍射级次范围（`order_min` 到 `order_max`）

### `solve_baseline(problem)` 输出
返回字典：
- `transitions`：跃迁向量
- `x_focus`：焦平面 x 轴网格
- `intensity_focus`：焦线上强度
- `metrics`：级次统计指标

## Baseline 当前实现
当前 baseline 用固定边界内均匀间隔跃迁，然后：
1. 生成单周期二值相位掩膜
2. 重复周期构造完整光栅
3. 叠加透镜相位
4. 用 `RS` 传播到焦面
5. 在每个级次窗口积分能量

## Oracle 当前实现
评测会计算两个强参考并取高分：
1. 文献跃迁表（diffractio Dammann 示例）
2. SciPy 差分进化（`scipy.optimize.differential_evolution`）

最终 oracle：`best_of_literature_and_scipy_de`。

## 指标与分数（越高越好）
原始指标：
- `cv_orders`（越小越好）
- `efficiency`（越大越好）
- `min_to_max`（越大越好）

分数公式：
- `uniform_score = clip(1 - cv_orders / 0.9, 0, 1)`
- `efficiency_score = clip((efficiency - 0.003) / (0.18 - 0.003), 0, 1)`
- `balance_score = clip((min_to_max - 0.15) / (0.90 - 0.15), 0, 1)`
- `score_pct = 100 * (0.60*uniform_score + 0.30*efficiency_score + 0.10*balance_score)`

范围：`0 ~ 100`，越高越好。

## valid 判定
- `cv_orders <= 0.8`
- `efficiency >= 0.003`
- `min_to_max >= 0.15`

## 可行优化方向
- 在跃迁向量上做约束优化
- 利用对称性降低维度
- 在均匀性与效率之间做权衡
- 加最小间距约束提升可制造性

