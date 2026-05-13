# AES-128 CTR 算法加速

我们提供了不使用第三方库的基础 C++ 实现 `baseline/AES-128.cpp`，你需要修改这个文件，在保持正确性的前提下提高算法吞吐率
`references/AES.pdf` 是算法详细介绍文件
运行 `verification/valid.sh` 会生成随机数据对算法正确性进行验证（使用OpenSSL）。
运行 `verification/eval.sh` 会分别使用 8Kbits 和 8Mbits 两种数据流进行多次运算，计算算法实现效率。

## 使用 frontier_eval 运行（unified）

unified benchmark：`task=unified task.benchmark=Cryptographic/AES-128`

```bash
python -m frontier_eval task=unified task.benchmark=Cryptographic/AES-128 algorithm.iterations=0
```

兼容别名（通过配置路由到相同 unified benchmark）：`task=crypto_aes128`。
