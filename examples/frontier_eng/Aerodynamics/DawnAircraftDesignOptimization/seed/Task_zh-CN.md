# Dawn 飞机设计优化（DawnAircraftDesignOptimization）

## 1. 背景

概念飞机尺寸设计是一个强耦合工程优化问题：任务目标（载荷、巡航高度、续航）会与气动、结构、动力系统相互制约。本任务用简化但带约束的模型刻画这种耦合。

任务灵感来自：
- `https://github.com/peterdsharpe/DawnDesignTool`
- 参考脚本：`design_opt.py`

## 2. 任务定义

在固定任务剖面下，选择飞机设计变量，使总重量最小，同时满足所有可行性约束。

固定任务输入来自 `references/mission_config.json`：

- 载荷质量
- 巡航高度
- 续航时长

## 3. 决策变量

提交包含 7 个连续变量：

- `wing_span_m`
- `wing_area_m2`
- `fuselage_length_m`
- `fuselage_diameter_m`
- `motor_power_kw`
- `battery_mass_kg`
- `cruise_speed_mps`

变量上下界由 `references/mission_config.json` 定义并强制检查。

## 4. 物理与性能模型

评测器采用简化概念模型，包含：

- 巡航高度标准大气密度
- 质量分解（机翼、机身、尾翼、起落架、动力、系统）
- 巡航升阻与巡航功率需求
- 失速速度与起飞滑跑距离估计
- 机翼根部应力估计
- 电池可用能量与任务能耗需求
- 翼载与几何比例

## 5. 约束条件

仅当所有约束裕度均 `>= 0` 时，设计才可行：

- 展弦比上下界
- 机身细长比下界
- 起飞距离上界
- 失速速度上界
- 巡航升力能力
- 根部应力上界
- 续航能量约束
- 巡航功率裕度约束
- 翼载上界

## 6. 目标与评分

### 目标

在约束满足前提下最小化 `total_mass_kg`。

### 评测输出指标

- `total_mass_kg`
- `cruise_power_kw`
- `takeoff_distance_m`
- `stall_speed_mps`
- `aspect_ratio`
- `feasible`
- `valid`
- `combined_score`

### 组合分数

若可行：

```text
combined_score = mass_reference_kg / (mass_reference_kg + total_mass_kg)
```

若不可行：

```text
combined_score = 0
valid = 0
```

## 7. 输入输出契约

### 候选程序输入

候选程序通过以下方式运行：

```bash
python scripts/init.py
```

可读取：

- `references/mission_config.json`

### 必需输出

候选程序必须生成 `submission.json`，且包含全部 7 个数值键。

缺失键、非数值、非有限值、越界值均视为无效。

## 8. 评测命令

评测候选脚本：

```bash
python verification/evaluator.py scripts/init.py
```

评测已有提交文件：

```bash
python verification/evaluator.py --submission submission.json
```

框架接入测试：

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Aerodynamics/DawnAircraftDesignOptimization \
  task.runtime.use_conda_run=false \
  algorithm.iterations=0
```

## 9. Baseline

基线候选程序为 `scripts/init.py`（同步副本 `baseline/solution.py`）：

- 物理模型与约束逻辑只读
- `solve_design()` 可修改
- 基线策略：多起点局部搜索 + 有限差分梯度步 + 约束罚函数
