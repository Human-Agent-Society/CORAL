# SPMe-T-Aging 建模说明

这个任务围绕一个面向控制优化的模型层级来设计，位于简单等效电路模型与完整多孔电极求解器之间。

## 为什么要有这个任务

纯 ECM 快充任务虽然便宜，但无法表达快充中最关键的内部限制：

- 固相表面饱和，
- 电解液极化，
- 析锂风险边界的移动，
- 温度导致的动力学变化，
- 高应力下 SEI 增长加速。

完整 P2D / DFN 模型虽然更接近机理，但通常太重，不适合大规模搜索、强化学习、MPC benchmark 或 AI agent 迭代优化。

因此这个任务选择中间层：

- `SPMe 风格电化学降阶`
- `集总热耦合`
- `半经验析锂与老化代理`

## 状态变量

评测器跟踪以下状态：

- 负极平均化学计量比，
- 负极表面偏移量，
- 正极平均化学计量比，
- 正极表面偏移量，
- 电解液极化状态，
- 集总温度，
- 累积析锂损失代理，
- 累积 SEI 老化代理。

之所以选这些状态，是因为它们直接对应了快充的关键失效模式。

## 降阶电化学结构

### 1. 固相动力学

模型采用降阶单颗粒解释：

- 平均化学计量比随充电量变化，
- 表面偏移量通过一阶松弛代理演化，
- 表面化学计量比决定 OCV 和动力学应力。

这样可以保留一个很重要的控制现象：大电流会在短时间内把表面状态推得比体相状态更激进。

### 2. 电解液极化

模型单独加入了电解液极化状态，因此：

- 大电流会提高液相过电势，
- 即使颗粒体相还没饱和，端电压也可能提前抬升，
- 在高电流浓差应力下，析锂风险会更严重。

这也是它比纯固相模型或 ECM-only 任务更真实的主要原因之一。

### 3. 动力学过电势

评测器使用带 `asinh` 结构的 Butler-Volmer 风格代理。交换电流代理取决于：

- 电极表面化学计量比，
- 温度，
- 电解液极化因子。

这使得高电流充电在触碰硬约束之前，就已经会体现出更高的电化学代价。

## 热耦合

任务使用集总热模型：

- 不可逆热来自端电压相对于 OCV 的损失，
- 可逆热通过熵项近似，
- 通过一阶散热项向环境放热。

温度会再通过 Arrhenius 风格乘子反馈到电化学状态中。在这个任务里，它会影响：

- 固相扩散时间常数，
- 交换电流代理，
- 欧姆电阻，
- 析锂与老化严重度。

## 析锂约束

评测器会计算一个降阶的析锂裕度，来源包括：

- 负极 OCV 项，
- 负极动力学过电势，
- 电解液极化惩罚，
- 低温惩罚。

当这个裕度缩小时：

- 析锂损失会增加，
- plating score 会变差，
- 若裕度过低则直接判无效。

这会产生与真实快充控制器非常相似的决策压力：即使电压和温度还没越界，策略也可能已经从析锂角度变得不安全。

## 老化模型

老化代理描述的是类 SEI 副反应增长：

- 温度越高越严重，
- 电化学应力越强越严重，
- 与析锂相关应力耦合。

它并不追求化学机理上的严格精确，而是为了让“虽然可行但太激进”的策略在优化上付出代价。

## 配置哲学

所有可调参数都放在：

- `references/battery_config.json`

用户可以修改：

- 电池容量和 SOC 窗口，
- 热限制，
- 电流限制，
- 化学计量边界，
- 电化学时间常数，
- 动力学系数，
- 热参数，
- 析锂 / 老化惩罚系数，
- 评分权重。

这个任务被刻意设计成参数化形式，方便在不修改评测器代码的情况下表示不同电芯或不同假设工况。

## 适用场景

这个 benchmark 适合：

- 进化搜索，
- agent 代码优化，
- 启发式分段快充设计，
- 低维控制序列上的 MPC 风格策略搜索，
- 基于多参数文件的鲁棒性研究。

## 参考资料

- [Moura et al. (2017): Battery State Estimation for a Single Particle Model with Electrolyte Dynamics](https://ieeexplore.ieee.org/document/8017015)
- [Bizeray et al. (2016): Reduced-order models of lithium-ion batteries for control applications](https://www.sciencedirect.com/science/article/pii/S0378775316310078)
- [Perez et al. (2017): Optimal charging of Li-ion batteries with coupled electro-thermal-aging dynamics](https://www.sciencedirect.com/)
- [Nature Energy (2019): Challenges and opportunities towards fast-charging battery materials](https://www.nature.com/articles/s41560-019-0405-3)
- [Nature Communications (2023): Extreme fast charging of commercial Li-ion batteries via combined thermal switching and self-heating approaches](https://www.nature.com/articles/s41467-023-38823-9)
