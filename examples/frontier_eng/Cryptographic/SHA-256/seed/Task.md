# SHA-256 (Secure Hash Algorithm 256-bit) Algorithm Acceleration

SHA-256 is a member of the SHA-2 hash function family released by the National Institute of Standards and Technology (NIST). It can compute a fixed-length 256-bit (32-byte) message digest for input data of arbitrary length.

SHA-256 is based on the traditional Merkle-Damgård construction. First, the input message is padded so that its bit length modulo 512 is congruent to 448, and 64 bits of the original message length information are appended, ensuring the final length is strictly a multiple of 512 bits. Then, the data is iteratively processed block by block, using the initial hash value and a compression function consisting of complex logical operations (bit operations, modulo addition, etc.), ultimately outputting a 256-bit hash value.

Your task is to modify `baseline/SHA-256.cpp` to improve its algorithm implementation efficiency (throughput). Note that the algorithm's correctness will be verified during the evaluation.

For detailed algorithm content and input/output, please refer to the `references`.