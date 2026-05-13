# Dawn 飞机设计优化

在给定任务需求下（巡航高度、续航时间、载荷），通过调整机翼、机身、动力和电池参数完成固定翼概念设计。

该任务受 `DawnDesignTool/design_opt.py` 启发，但被整理为“单文件可演化候选程序 + 独立评测器”的基准形式。

## 文件说明

- `Task.md`：完整任务定义与评分规则
- `references/mission_config.json`：任务目标、变量边界、常量与约束
- `scripts/init.py`：可演化基线候选程序（核心可改函数为 `solve_design()`）
- `verification/evaluator.py`：独立评测器
- `verification/requirements.txt`：运行依赖
- `baseline/solution.py`：`scripts/init.py` 的基线副本
- `frontier_eval/`：unified 框架接入元数据

## 快速开始

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线候选程序

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python scripts/init.py
# 输出: submission.json
```

### 3. 直接评测候选程序

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python verification/evaluator.py scripts/init.py
```

### 4. 评测已有提交文件

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python verification/evaluator.py --submission submission.json
```

### 5. 使用 frontier_eval 运行（unified）

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Aerodynamics/DawnAircraftDesignOptimization \
  task.runtime.use_conda_run=false \
  algorithm.iterations=0
```

等价的命名任务配置：

```bash
python -m frontier_eval task=dawn_aircraft_design_optimization algorithm.iterations=0
```

## 提交格式

`submission.json` 必须是包含以下数值字段的 JSON 对象：

```json
{
  "wing_span_m": 26.0,
  "wing_area_m2": 24.0,
  "fuselage_length_m": 9.0,
  "fuselage_diameter_m": 0.9,
  "motor_power_kw": 45.0,
  "battery_mass_kg": 170.0,
  "cruise_speed_mps": 27.0
}
```

字段含义与边界见 `references/mission_config.json`。

## 评分摘要

- 主目标：最小化 `total_mass_kg`
- 可行性：必须同时满足起飞、升力、结构强度、续航能量、功率裕度、翼载、机身细长比、展弦比等约束
- 评分：
  - 可行：`combined_score = mass_reference_kg / (mass_reference_kg + total_mass_kg)`
  - 不可行：`combined_score = 0`，`valid = 0`

## 可修改边界

演化目标文件为 `scripts/init.py`。

- 保持 `EVOLVE-BLOCK-START` 与 `EVOLVE-BLOCK-END` 标记不变。
- 物理模型、约束定义和输出契约视为只读。
- 主要修改 `solve_design()`，尝试更优设计变量组合或求解策略。

