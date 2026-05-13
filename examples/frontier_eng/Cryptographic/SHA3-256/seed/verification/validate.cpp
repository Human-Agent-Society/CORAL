#include <iostream>
#include <vector>
#include <string>
#include <fstream>
#include <random>
#include <iomanip>
#include <sstream>
#include <cstdio>
#include <memory>
#include <array>
#include <openssl/evp.h> 


std::string openssl_sha3_256(const std::vector<uint8_t>& data) {
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    const EVP_MD* md = EVP_sha3_256();
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int lengthOfHash = 0;

    EVP_DigestInit_ex(context, md, nullptr);
    EVP_DigestUpdate(context, data.data(), data.size());
    EVP_DigestFinal_ex(context, hash, &lengthOfHash);
    EVP_MD_CTX_free(context);

    std::ostringstream oss;
    for (unsigned int i = 0; i < lengthOfHash; ++i) {
        oss << std::hex << std::setw(2) << std::setfill('0') << (int)hash[i];
    }
    return oss.str();
}


void write_data_to_file(const std::string& filepath, const std::vector<uint8_t>& data) {
    std::ofstream file(filepath, std::ios::binary);
    if (file.is_open()) {
        file.write(reinterpret_cast<const char*>(data.data()), data.size());
        file.close();
    } else {
        std::cerr << "无法创建测试文件: " << filepath << std::endl;
        exit(1);
    }
}


std::string exec_custom_sha3(const std::string& cmd) {
    std::array<char, 128> buffer;
    std::string result;
    
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd.c_str(), "r"), pclose);
    if (!pipe) {
        throw std::runtime_error("popen() 失败！");
    }
    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
        result += buffer.data();
    }
    
    
    result.erase(result.find_last_not_of(" \n\r\t") + 1);
    return result;
}

int main() {
    
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> len_dist(0, 5000); 
    std::uniform_int_distribution<> byte_dist(0, 255); 

    const int TEST_COUNT = 10;
    const std::string TEST_FILE = "temp_test_input.bin";
    
    const std::string CUSTOM_EXEC = "./custom_sha3"; 

    int passed = 0;

    std::cout << "开始交叉验证 (共 " << TEST_COUNT << " 组随机测试)..." << std::endl;
    std::cout << std::string(60, '-') << std::endl;

    for (int i = 0; i < TEST_COUNT; ++i) {
        
        int data_length = len_dist(gen);
        std::vector<uint8_t> random_data(data_length);
        for (int j = 0; j < data_length; ++j) {
            random_data[j] = static_cast<uint8_t>(byte_dist(gen));
        }

        
        write_data_to_file(TEST_FILE, random_data);

        
        std::string expected_hash = openssl_sha3_256(random_data);

        
        
        std::string command = CUSTOM_EXEC + " " + TEST_FILE;
        std::string custom_hash;
        try {
            custom_hash = exec_custom_sha3(command);
        } catch (const std::exception& e) {
            std::cerr << "执行自定义程序失败，请检查是否已编译为 custom_sha3: " << e.what() << std::endl;
            return 1;
        }

        
        bool is_match = (expected_hash == custom_hash);
        if (is_match) passed++;

        std::cout << "测试 #" << (i + 1) << " (长度: " << data_length << " bytes)" << std::endl;
        std::cout << "OpenSSL : " << expected_hash << std::endl;
        std::cout << "Custom  : " << custom_hash << std::endl;
        std::cout << "结果    : " << (is_match ? "\033[32m[PASS]\033[0m" : "\033[31m[FAIL]\033[0m") << std::endl;
        std::cout << std::string(60, '-') << std::endl;
    }

    std::cout << "验证完成！通过率: " << passed << "/" << TEST_COUNT << std::endl;

    
    std::remove(TEST_FILE.c_str());

    return 0;
}