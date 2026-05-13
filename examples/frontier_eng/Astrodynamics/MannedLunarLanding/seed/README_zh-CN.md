# 载人登月（天体力学）

本目录包含任务说明、用于生成 `results.txt` 的基线脚本，以及用于检验结果文件的 MATLAB/Octave 验证程序。

## 主要文件与作用

- `Task.md`
  - 作业说明：任务背景、模型定义、约束条件、事件编码与 `results.txt` 格式。

- `scripts/init.py`
  - 基于 CR3BP 的基线轨道生成器（地球出发 → 月球到达/LOI → 月面停留 → TEI → 地球返回）。
  - 计算质量预算并在当前工作目录写出 `results.txt`。
  - 预留 L1 Lyapunov 补给飞船模型（`SupplyShip` 仍为 TODO）。

- `eval/error_checking_program.m`
  - MATLAB 验证程序，读取 `results.txt` 并检查：
    - 事件完整性与顺序
    - 时间单调与总任务时长
    - 出发/到达轨道约束
    - 机动 Δv 与燃料消耗一致性
    - 滑翔段递推精度与高度边界
    - 可选补给飞船对接约束
    - 返回地球条件与剩余燃料限制
  - 生成 `outputlog.txt` 并绘制轨迹。

- `eval/aerodynamics_check_octave_full.m`
  - Octave 兼容版验证程序（检查逻辑一致，`findpeaks` 调用方式调整）。
  - 生成 `outputlog.txt` 供查看。

## 生成文件

- `results.txt`
  - 由 `scripts/init.py`（或你的求解器）生成，必须符合 `Task.md` 中的格式要求。

- `outputlog.txt`
  - 由 MATLAB/Octave 验证程序输出的检查报告。

## 常见流程

如果你的机器还没有安装 Octave，可以先执行：

```bash
bash scripts/bootstrap/install_host_deps.sh --octave
```

1. 编写/修改求解器生成 `results.txt`（可参考 `scripts/init.py`）。
2. 在 `eval/` 目录运行 MATLAB 或 Octave 验证程序进行检查。
3. 迭代优化直至所有检查通过，并尽量提升运载质量。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Astrodynamics/MannedLunarLanding`

```bash
python -m frontier_eval task=unified task.benchmark=Astrodynamics/MannedLunarLanding algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=manned_lunar_landing`。
