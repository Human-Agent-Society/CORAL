# 可微全息 H3：多波长聚焦/分束

## 背景

同一个衍射器件往往需要在多个波长下同时工作。
该任务模拟光谱设计需求：不同波长需要被引导到指定区域，并满足整体光谱功率平衡目标。

应用示例：

- 彩色成像光学，
- WDM 波分路由，
- 色差补偿设计。

## agent 需要修改的内容

- 目标文件：`baseline/init.py`

## 目录结构

```text
task3_multispectral_focusing/
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
$PY benchmarks/Optics/holographic_multispectral_focusing/verification/evaluate.py
```

结果会输出到 `verification/artifacts/`。

## Oracle 依赖

`verification/reference_solver.py` 使用第三方库 `slmsuite` 作为上界 oracle 后端。
实现包含 WGS 初始化与 `torchoptics` 下的按波长独立微调。
