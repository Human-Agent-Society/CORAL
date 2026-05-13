# 车辆空气动力学感知

在固定的 3D 汽车表面上选择 30 个传感器位置，以最小化全场压力重建误差。

## 文件说明
- `Task.md`：任务说明与规则
- `references/`：参考点集与生成脚本
- `verification/`：评测器与运行环境
- `baseline/`：随机采样基线

## 快速开始
如果你希望仓库自动把默认的代码 / 数据 / 权重目录准备好，可以先执行：

```bash
python scripts/bootstrap/fetch_task_assets.py --target car-aero
```

0) 准备 PhySense 代码（评测必需）：
- 推荐：
  - `git clone https://github.com/thuml/PhySense.git third_party/PhySense`
- 默认路径：`third_party/PhySense/Car-Aerodynamics/`
- 备选：
  - `<workspace>/PhySense/Car-Aerodynamics/`（与 `Frontier-Engineering/` 同级）
  - 设置 `PHYSENSE_ROOT=/path/to/PhySense`（也可以直接指到 `Car-Aerodynamics/` 目录）

1) 从 PhySense 下载数据与预训练模型：
- 数据集：https://drive.google.com/drive/folders/1Xt395uC-RreWQ_bh5v_Bu-AOwV6SRt_w?usp=share_link
- 预训练模型：https://drive.google.com/drive/folders/1kODTzH5n_njQ7lgL-2i2aXbt33UjGKk9?usp=sharing

2) 将文件放到以下**固定路径**（相对于本任务目录）：
- 数据集根目录：`data/physense_car_data/`
  - 必须包含 `pressure_files/` 和 `velocity_files/`
- 基座模型权重：`data/physense_car_ckpt/physense_transolver_car_base.pth`（或 `data/physense_car_ckpt/physense_transolver_car_best_base.pth`）

3) 生成参考点集：

```bash
python references/extract_car_mesh.py \
  --data-dir data/physense_car_data \
  --output references/car_surface_points.npy
```

4) 生成基线提交：

```bash
python baseline/solution.py --output submission.json
```

5) 评测：

```bash
python verification/evaluator.py --submission submission.json
```

## Docker（构建上下文）
请以 `verification/` 目录作为构建上下文：

```bash
cd verification
docker build -f docker/Dockerfile -t car-aero-eval .
```

## 备注
- 需要 GPU。评测器使用 CUDA，CPU 环境会失败。
- 评测器从 case_76 到 case_100 中以种子 2025 抽取 K=10 个工况。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Aerodynamics/CarAerodynamicsSensing`

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Aerodynamics/CarAerodynamicsSensing task.runtime.env_name=frontier-v1-kernel algorithm.iterations=0
```

运行 unified 评测前，仍需先准备上面列出的 PhySense 代码、数据集、模型权重以及参考点文件。

兼容别名（通过配置路由到相同 unified benchmark）：`task=car_aerodynamics_sensing`。
