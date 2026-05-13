# 可微全息 H1：多焦点相对光强配比控制

## 背景

这是典型的衍射光学器件（DOE）设计问题：
在指定位置形成多个焦点，同时满足焦点之间的目标功率配比。

典型场景：

- 并行激光加工，
- 多光阱光镊控制，
- 多通道自由空间耦合。

## agent 需要修改的内容

- 目标文件：`baseline/init.py`
- 任务设定下其它文件默认只读。

## 目录结构

```text
task1_multifocus_power_ratio/
  baseline/
    init.py
  verification/
    evaluate.py
    reference_solver.py
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## 环境依赖

推荐解释器：

```bash
python
```

共享任务依赖文件：

- `benchmarks/Optics/requirements.txt`

安装示例（在仓库根目录执行）：

```bash
PY=python3
$PY -m pip install -r benchmarks/Optics/requirements.txt
$PY -m pip install -e .
```

如果只运行 baseline 且跳过 oracle，可以从该 requirements 文件中移除 `slmsuite`/`scipy`。

## 运行方式

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py
```

可选参数：

- `--device cpu|cuda`
- `--baseline-steps N`
- `--reference-steps N`
- `--seed N`

## 输出产物

评测会生成：

- `verification/artifacts/summary.json`
- `verification/artifacts/intensity_maps.png`
- `verification/artifacts/ratios_and_losses.png`

## Oracle 依赖

`verification/reference_solver.py` 使用第三方库 `slmsuite` 作为 oracle 后端。
