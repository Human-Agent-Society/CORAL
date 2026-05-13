# 三角形乘法

此任务源自 https://www.gpumode.com/leaderboard/496?tab=rankings

TriMul 参考实现位于 `baseline/reference.py` 这里是基础实现，同时也是数值正确性的标准
`baseline/solution.py` 是 `test-time-training` 所提供的实现
agent 可以基于 `baseline/submission.py` 进行修改，这是待优化的模板版本
`baseline/util.py` 提供公共工具
评测入口位于 `verification/eval.py`
`verification/eval-profile.py` 是带细粒度计时诊断版，用于定位时间花在哪
`verification/requirements-gpumode.txt` 提供所需依赖

## 运行方式

```
cd benchmarks/KernelEngineering/TriMul/verification

# 只检验正确性
exec 3>tri_test.log POPCORN_FD=3 python eval.py test tri_tests.txt

# 每个case计时，只做一次初始正确性检查，后续主要测试速度
exec 3>tri_bench.log POPCORN_FD=3 python eval.py benchmark tri_bench.txt

# 每个case计时，会在循环中反复换 seed 并重新做正确性校验，更严格
exec 3>tri_leaderboard.log POPCORN_FD=3 python eval.py benchmark tri_bench.txt
```

上述代码会使用`submission.custom_kernel` 进行评测，您可以选择将`benchmarks/KernelEngineering/TriMul/baseline/submission.py`替换为您的代码，或者将 `benchmarks/KernelEngineering/TriMul/verification/eval.py` 中所有的 `from baseline.submission import custom_kernel` 替换为从您指定的代码中 import

## 在 frontier_eval 中的评测方式

`frontier_eval` 接入 TriMul 的逻辑位于：

- `frontier_eval/tasks/trimul/task.py`
- `frontier_eval/tasks/trimul/evaluator/python.py`

整体流程如下：

1. 初始候选代码使用 `benchmarks/KernelEngineering/TriMul/baseline/submission.py`。
2. 每次评测会创建临时沙箱目录，将 `baseline/` 与 `verification/` 复制进去。
3. 将当前候选代码覆盖到沙箱内的 `baseline/submission.py`。
4. 默认执行：
   - `python eval.py benchmark tri_bench.txt`
5. 若遇到 `PermissionError` + `SemLock`，会自动退化为串行 wrapper，并执行：
   - `python _serial_eval_runner.py benchmark tri_bench_24g.txt`
6. 从 `tri_bench.log` 解析每个 case 的 `mean`，计算几何平均 `geom_mean_ns`。
7. 速度分数先按 `combined_score = 1e9 / geom_mean_ns` 计算；但只有在以下条件全部满足时才算有效：
   - 进程返回码为 0
   - `check == pass`
   - 有有效 benchmark 均值
   否则会强制置 `valid=0` 且 `combined_score=0`。

评测产物（stdout/stderr、tri_bench.log、错误摘要等）会作为 artifacts 返回给 OpenEvolve，并在后续迭代 prompt 的 `Last Execution Output` 中提供给模型。当前实现也会注入：

- `task_spec_zh_cn_path`
- `task_spec_zh_cn`（`Task_zh-CN.md` 内容，按上限截断）

### 使用 frontier_eval 运行 TriMul（unified，示例）

```bash
OPENAI_MODEL=qwen/qwen3-coder-next \
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=KernelEngineering/TriMul \
  task.runtime.env_name=frontier-v1-kernel \
  algorithm.iterations=20 \
  algorithm.oe.evaluator.timeout=1800
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=trimul`。
