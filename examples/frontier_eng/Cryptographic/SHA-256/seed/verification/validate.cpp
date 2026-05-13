#include <iostream>
#include <string>
#include <vector>
#include <random>
#include <iomanip>
#include <sstream>
#include <fstream>
#include <cstdio>
#include <memory>
#include <array>
#include <stdexcept>

#include <openssl/sha.h>


std::string generate_random_string(size_t length) {
    const std::string characters = 
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!@#$%^&*()_+~`|}{[]:;?><,./-=";
    std::random_device random_device;
    std::mt19937 generator(random_device());
    std::uniform_int_distribution<> distribution(0, characters.size() - 1);

    std::string random_string;
    for (size_t i = 0; i < length; ++i) {
        random_string += characters[distribution(generator)];
    }
    return random_string;
}


std::string openssl_sha256(const std::string& input) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char*>(input.c_str()), input.length(), hash);
    
    std::stringstream ss;
    for(int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        ss << std::hex << std::setw(2) << std::setfill('0') << (int)hash[i];
    }
    return ss.str();
}


std::string exec_custom_sha(const std::string& input_file, const std::string& exec_path) {
    
    std::string command = exec_path + " < " + input_file;
    std::array<char, 128> buffer;
    std::string result;
    
    
#ifdef _WIN32
    std::unique_ptr<FILE, decltype(&_pclose)> pipe(_popen(command.c_str(), "r"), _pclose);
#else
    std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(command.c_str(), "r"), pclose);
#endif

    if (!pipe) {
        throw std::runtime_error("Failed to run custom SHA256 executable. Check if the path is correct.");
    }
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr) {
        result += buffer.data();
    }
    
    
    result.erase(result.find_last_not_of(" \n\r\t") + 1);
    return result;
}

int main() {
    
#ifdef _WIN32
    const std::string custom_exec_path = "custom_sha.exe";
#else
    const std::string custom_exec_path = "./custom_sha";
#endif

    const std::string temp_file = "temp_test_input.bin";
    const int num_tests = 10;
    
    
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> len_dist(0, 2000); 
    
    int passed_count = 0;

    std::cout << "Starting SHA-256 Verification (" << num_tests << " random sequences)...\n";
    std::cout << std::string(80, '-') << "\n";

    for (int i = 1; i <= num_tests; ++i) {
        size_t seq_length = len_dist(gen);
        std::string test_seq = generate_random_string(seq_length);
        
        
        std::string expected_hash = openssl_sha256(test_seq);
        
        
        std::ofstream out(temp_file, std::ios::binary);
        if (!out) {
            std::cerr << "Error creating temporary file.\n";
            return 1;
        }
        out.write(test_seq.c_str(), test_seq.size());
        out.close();
        
        
        std::string actual_hash;
        try {
            actual_hash = exec_custom_sha(temp_file, custom_exec_path);
        } catch (const std::exception& e) {
            std::cerr << "Execution error: " << e.what() << "\n";
            std::remove(temp_file.c_str());
            return 1;
        }

        
        bool is_match = (expected_hash == actual_hash);
        if (is_match) passed_count++;

        std::cout << "Test [" << std::setw(2) << std::setfill('0') << i << "] | Length: " << std::setw(4) << std::setfill(' ') << seq_length << " bytes\n";
        std::cout << "OpenSSL : " << expected_hash << "\n";
        std::cout << "Custom  : " << actual_hash << "\n";
        std::cout << "Result  : " << (is_match ? "\033[32m[PASS]\033[0m" : "\033[31m[FAIL]\033[0m") << "\n";
        std::cout << std::string(80, '-') << "\n";
    }

    
    std::remove(temp_file.c_str());

    std::cout << "Verification Complete: " << passed_count << "/" << num_tests << " passed.\n";

    return (passed_count == num_tests) ? 0 : 1;
}