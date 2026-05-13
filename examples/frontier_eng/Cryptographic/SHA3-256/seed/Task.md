# SHA3-256 (Secure Hash Algorithm 3 256-bit)

SHA3-256 is the latest generation hash function standard selected by NIST through the Open Cryptography Competition (FIPS 202). It uses the Keccak algorithm at its core and also outputs a 256-bit digest.

SHA3-256 employs a sponge construction that is significantly different from SHA-2. It relies on a massive 1600-bit internal state space and is mainly divided into two stages:

- **Absorbing Stage**: The input message is divided into blocks according to a set bitrate, XORed with the first half of the state space, and the Keccak-f core permutation function is applied to the entire state space.

- **Squeezing Stage**: After absorbing all the message, the required length (256 bits) of hash output is directly extracted from the first half of the state space.

Your task is to modify `baseline/SHA3-256.cpp` to improve its algorithm implementation efficiency (throughput). Note that the algorithm's correctness will also be verified during evaluation.

For detailed algorithm content and input/output, please refer to `references`.