# 车辆空气动力学感知（CarAerodynamicsSensing）

## 背景
汽车表面的气动压力会随工况变化。由于传感器成本高且数量受限，需要在表面上放置少量传感器，以尽可能准确地重建全场压力分布。

## 任务
给定固定的 3D 汽车表面点集，选择 **N = 30** 个传感器位置（点索引），使未见测试工况上的全场压力重建误差最小。

## 输入
- `references/car_surface_points.npy`：形状为 `(M, 3)` 的 numpy 数组，记录表面点坐标。提交的索引必须指向该数组。
- 汽车空气动力学数据集（外部下载，见 `README.md`）。
- PhySense 仓库（模型代码，评测必需）。评测器默认会在 `third_party/PhySense/Car-Aerodynamics/` 查找，或可通过 `PHYSENSE_ROOT=/path/to/PhySense` 指定（也可以直接指到 `Car-Aerodynamics/` 目录）。

## 输出
生成 `submission.json`，格式如下：

```json
{
  "indices": [12, 480, 932,  ...  , 95427]
}
```

约束：
- 必须包含 30 个索引。
- 索引 **从 0 开始** 且 **唯一**。
- 每个索引需满足 `0 <= index < M`。

## 数据与预处理
- 原始压力文件：`data/physense_car_data/pressure_files/case_{i}_p_car_patch.raw`（相对于任务目录）。
- 每行包含 `x y z p`（坐标与压力）。
- 使用 3 sigma 裁剪去除离群值。
- 压力归一化：
  - `p_min = -844.3360`
  - `p_max =  602.6890`
  - `p_norm = (p - p_min) / (p_max - p_min)`
- `car_surface_points.npy` 通过对 `case_1` 应用相同的 3 sigma 裁剪生成。

## 评测
- 测试工况为 `case_76` 到 `case_100`（共 25 个）。
- 评测使用固定随机种子（**2025**）抽取 **K = 10** 个工况计分。
- 对每个测试工况：
  1. 载入并预处理压力场。
  2. 将提交索引映射到参考点。
  3. 将参考点匹配到该工况中最近的表面点。
  4. 使用预训练 Transolver 基座模型重建全场压力。
  5. 计算 Relative L2 Error：
     `rel_l2 = ||p_gt - p_pred||_2 / ||p_gt||_2`。
- 最终得分：
  - `score = 1.0 - mean(rel_l2)`（对 K 个工况求平均）。
  - 分数越高越好。

## Baseline
`baseline/solution.py` 会从参考点集中随机采样 30 个索引并写入 `submission.json`。
