# 工业背景与建模说明

这个 benchmark 是降阶模型任务，但任务结构是按照工业界真实的快充优化问题来设计的。

## 真实工程需求是什么

在真实充电系统里，优化目标几乎从来不是“只要更快”。工程上通常要同时考虑：

- `达到目标的时间`：例如从低 SOC 到 `80%` SOC 的充电时间。
- `硬安全约束`：端电压、温度、紧急截止条件。
- `避免析锂`：低温、高 SOC、大电流下，负极电势可能进入危险区间。
- `寿命影响`：长期激进快充会加速 SEI 增长、活性锂损失和阻抗升高。
- `可实现性`：很多量产充电器仍更偏好可用分段 CC、查表或低阶 MPC 表示的策略。

这也是为什么本任务让用户优化“分段恒流协议”，而不是任意连续波形控制。

## 工业界常见建模层级

### 等效电路模型

ECM 是电池管理系统里最常见的一类模型，因为它们容易标定，计算开销也足够低，适合嵌入式在线控制。常见组成包括：

- OCV-SOC 关系，
- 欧姆内阻，
- 一个或多个 RC 极化支路，
- 可选的热耦合状态。

这类模型广泛用于状态估计、在线限流和上层充电逻辑。

### 降阶电化学模型

当工程师需要更认真地处理扩散限制或析锂风险时，常会进一步使用降阶电化学模型，例如：

- 单颗粒模型，
- 带电解液动力学的单颗粒模型，
- 电化学与等效电路混合模型。

这类模型仍适合做优化或离线协议搜索，但保留了更多有物理意义的内部状态。

### 高保真多孔电极模型

全阶 P2D / DFN 模型更适合：

- 机理研究，
- 设计空间分析，
- 离线协议验证，
- 为简单控制器生成训练或标注数据。

但在量产嵌入式控制里，它们通常过重、参数也更敏感，因此不常直接作为在线控制主模型。

## 这个任务如何映射到上述体系

本任务的评测器内部使用一个确定性的代理模型，包含：

- 非线性 OCV 曲线，
- 与 SOC、温度相关的内阻，
- 极化状态，
- 浓差代理状态，
- 集总热平衡，
- 析锂风险代理项，
- 老化损失代理项。

它不是化学机理上完全精确的数字孪生，而是为了保留最关键的优化张力：

- 前段敢于拉高电流，时间会更短；
- 在高 SOC 区持续大电流，电压压力会快速抬升；
- 大电流和较大浓差过电势会提高析锂倾向；
- 额外发热和析锂会转化为长期寿命成本。

## 用户可配置参数

所有电池与评测参数都集中在：

- `references/battery_config.json`

这个文件是任务的主要自定义入口。用户可以修改：

- 电池容量，
- 初始 / 目标 SOC，
- 环境温度，
- 电压和温度限制，
- 仿真时长，
- 电流边界，
- 降阶模型系数，
- 评分权重。

当前配置是一组针对通用 `3.0 Ah` 锂离子电芯的示例参数，不代表某个已验证的商业电芯实测标定集。

## 当前代理模型的含义

### OCV 模块

OCV 使用平滑的非线性函数，目的是让：

- 低到中 SOC 区间相对容易推进，
- 高 SOC 区的电压抬升更陡，
- 末段降流变得有实际意义。

### 内阻与极化

内阻和极化项被设计成：

- 低 SOC 和高 SOC 区更难充，
- 持续大电流会造成额外电压抬升，
- 温度变化会以合理方向影响等效内阻。

### 析锂代理项

真实析锂与负极局部过电势、温度、扩散限制、颗粒浓度梯度和电芯设计密切相关。本任务中用一个低阶“安全裕度”代理来表示，输入包括：

- SOC，
- 电流倍率，
- 浓差代理状态，
- 低温惩罚项。

这不是严格的电化学析锂模型，但会产生和真实快充优化相同的定性行为。

### 老化代理项

老化项综合考虑：

- 电流应力，
- 温度加速，
- 与析锂严重度耦合的额外惩罚。

这样就能区分“很快但很伤电池”和“快但相对克制”的策略。

## 为什么评测器保持确定性

评测器保持确定性，是因为 benchmark 需要：

- 可重复打分，
- 低方差，
- 本地快速验证，
- 兼容进化搜索和批量实验。

以后当然可以再加随机扰动或多工况鲁棒性层，但作为首版贡献，确定性评测是更稳妥的选择。

## 后续可扩展方向

这个任务未来最自然的升级方向包括：

- 多环境温度工况，
- CC-CV 尾段处理，
- pack 级热约束，
- 多组电芯参数切换，
- 从单工况最优扩展到鲁棒退化感知优化。

## 参考来源

- [Nature Energy (2019): Challenges and opportunities towards fast-charging battery materials](https://www.nature.com/articles/s41560-019-0405-3)
- [Nature Communications (2023): Extreme fast charging of commercial Li-ion batteries via combined thermal switching and self-heating approaches](https://www.nature.com/articles/s41467-023-38823-9)
- [Nature Energy (2023): Quantifying lithium plating for fast-charge protocol design](https://www.nature.com/articles/s41560-023-01194-y)
- [OSTI (2015): Lithium-ion battery cell-level control using constrained model predictive control and equivalent circuit models](https://www.osti.gov/biblio/1211079)
- [Journal of Energy Storage (2024): A novel hybrid electrochemical equivalent circuit model for online battery management systems](https://www.sciencedirect.com/science/article/pii/S2352152X24027282)
- [Journal of Energy Storage (2021): Fast charging lithium-ion battery formation based on simulations with an electrode equivalent circuit model](https://www.sciencedirect.com/science/article/abs/pii/S2352152X21001080)

## 如何理解这个 benchmark

这个任务应被理解为：

- 一个快充策略优化任务，
- 一个降阶工程 benchmark，
- 不是全阶电化学求解器 benchmark，
- 也不是电池参数辨识 benchmark。

核心挑战是在不依赖不现实激进电流的前提下，尽量高效地利用安全区域完成充电。
