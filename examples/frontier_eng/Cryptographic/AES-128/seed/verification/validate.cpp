#include <iostream>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <cstdlib>
#include <openssl/evp.h>
#include <openssl/rand.h>


std::string bytesToHex(const std::vector<uint8_t>& bytes) {
    std::ostringstream oss;
    for (uint8_t b : bytes) {
        oss << std::hex << std::setw(2) << std::setfill('0') << (int)b;
    }
    return oss.str();
}


std::vector<uint8_t> openssl_aes_ctr_encrypt(const std::vector<uint8_t>& plaintext, 
                                             const std::vector<uint8_t>& key, 
                                             const std::vector<uint8_t>& iv) {
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    std::vector<uint8_t> ciphertext(plaintext.size());
    int len;
    int ciphertext_len = 0;

    EVP_EncryptInit_ex(ctx, EVP_aes_128_ctr(), NULL, key.data(), iv.data());
    
    
    EVP_CIPHER_CTX_set_padding(ctx, 0);

    EVP_EncryptUpdate(ctx, ciphertext.data(), &len, plaintext.data(), plaintext.size());
    ciphertext_len = len;

    EVP_EncryptFinal_ex(ctx, ciphertext.data() + len, &len);
    ciphertext_len += len;

    EVP_CIPHER_CTX_free(ctx);
    ciphertext.resize(ciphertext_len);
    return ciphertext;
}

int main() {
    const int TEST_COUNT = 10;
    std::vector<std::vector<uint8_t>> expected_ciphertexts;
    std::vector<size_t> plaintext_lengths;

    std::ofstream infile("test_in.txt");
    if (!infile.is_open()) {
        std::cerr << "Error creating test_in.txt\n";
        return 1;
    }

    for (int i = 0; i < TEST_COUNT; ++i) {
        std::vector<uint8_t> key(16);
        std::vector<uint8_t> iv(16);
        
        
        int pt_len = (rand() % 100) + 1; 
        std::vector<uint8_t> plaintext(pt_len);

        RAND_bytes(key.data(), key.size());
        RAND_bytes(iv.data(), iv.size());
        RAND_bytes(plaintext.data(), plaintext.size());

        
        infile << bytesToHex(key) << "\n"
               << bytesToHex(iv) << "\n"
               << bytesToHex(plaintext) << "\n";

        
        expected_ciphertexts.push_back(openssl_aes_ctr_encrypt(plaintext, key, iv));
        plaintext_lengths.push_back(plaintext.size());
    }
    infile.close();

    int ret = system("./custom_aes");
    if (ret != 0) {
        std::cerr << "Failed to execute custom_aes. Ensure it is compiled correctly.\n";
        return 1;
    }

    std::ifstream outfile("test_out_custom.txt");
    if (!outfile.is_open()) {
        std::cerr << "Error opening test_out_custom.txt\n";
        return 1;
    }

    std::cout << "Starting AES-128-CTR Verification (" << TEST_COUNT << " random vectors)...\n";
    std::cout << std::string(80, '-') << "\n";

    std::string custom_hex;
    int pass_count = 0;
    for (int i = 1; i <= TEST_COUNT; ++i) {
        if (!std::getline(outfile, custom_hex)) {
            std::cerr << "Unexpected output: custom_aes produced fewer than " << TEST_COUNT << " lines.\n";
            outfile.close();
            return 1;
        }

        const std::string expected_hex = bytesToHex(expected_ciphertexts[i - 1]);
        const bool is_match = (custom_hex == expected_hex);
        if (is_match) {
            pass_count++;
        }

        std::cout << "Test [" << std::setw(2) << std::setfill('0') << i << "] | Length: "
                  << std::setw(4) << std::setfill(' ') << plaintext_lengths[i - 1] << " bytes\n";
        std::cout << "OpenSSL : " << expected_hex << "\n";
        std::cout << "Custom  : " << custom_hex << "\n";
        std::cout << "Result  : " << (is_match ? "\033[32m[PASS]\033[0m" : "\033[31m[FAIL]\033[0m") << "\n";
        std::cout << std::string(80, '-') << "\n";
    }
    outfile.close();

    std::cout << "Verification Complete: " << pass_count << "/" << TEST_COUNT << " passed.\n";
    return (pass_count == TEST_COUNT) ? 0 : 1;
}
