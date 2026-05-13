# AES-128 CTR (Advanced Encryption Standard, 128-bit key, Counter mode)
AES 是一种对称密钥分组密码（Symmetric-key block cipher），是目前广泛采用的国际加密标准。128 指代其密钥长度为 128 比特。CTR（计数器模式）是其标准支持的工作模式之一。

## 技术机制：
- **流密码转化**：CTR 模式将原本的分组密码转化为了同步流密码（Synchronous stream cipher）。
- **密钥流生成**：它不直接加密明文，而是通过对一个不断递增的计数器（Counter）及初始向量（Nonce/IV）的组合进行 AES 核心函数加密，从而生成伪随机的密钥流（Keystream）。
- **加密与解密**：明文（Plaintext）与上述生成的密钥流进行按位异或（XOR）运算生成密文（Ciphertext）。解密过程具有对合性（Involution），即密文与相同的密钥流再次异或即可还原出明文。

你的任务是修改 `baseline/AES-128.cpp`，提高其算法实现效率（吞吐率）。注意，评测时会同时验证算法正确性。
详细的算法内容以及输入输出请查看 `references`
