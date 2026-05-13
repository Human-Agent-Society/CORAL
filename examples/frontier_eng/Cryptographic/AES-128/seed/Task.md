# AES-128 CTR (Advanced Encryption Standard, 128-bit key, Counter mode)

AES is a symmetric-key block cipher and a widely adopted international encryption standard. 128 refers to its 128-bit key length. CTR (Counter mode) is one of the standard's supported operating modes.

## Technical Mechanism:

- **Stream Cipher Conversion**: CTR mode converts the original block cipher into a synchronous stream cipher.

- **Keystream Generation**: It does not directly encrypt plaintext. Instead, it generates a pseudo-random keystream by encrypting a combination of an incrementing counter and an initialization vector (Nonce/IV) using the AES core function.

- **Encryption and Decryption**: The plaintext is XORed with the generated keystream to generate ciphertext. The decryption process exhibits involution, meaning that the plaintext can be recovered by XORing the ciphertext with the same keystream.

Your task is to modify `baseline/AES-128.cpp` to improve its algorithm implementation efficiency (throughput). Note that the algorithm's correctness will also be verified during evaluation.

For detailed algorithm content and input/output, please refer to the `references`.