#include <chrono>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr size_t kSize8KBitsBytes = 1000;
constexpr size_t kSize8MBitsBytes = 1000000;
constexpr int kIterations8K = 500;
constexpr int kIterations8M = 50;
constexpr double kMinMbps = 100.0;

std::string bytes_to_hex(const std::vector<uint8_t>& bytes) {
    std::ostringstream oss;
    for (uint8_t value : bytes) {
        oss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(value);
    }
    return oss.str();
}

std::string random_hex(size_t num_bytes) {
    std::vector<uint8_t> data(num_bytes);
    for (size_t i = 0; i < num_bytes; ++i) {
        data[i] = static_cast<uint8_t>(std::rand() % 256);
    }
    return bytes_to_hex(data);
}

bool write_aes_input(const std::string& key_hex,
                     const std::string& iv_hex,
                     const std::string& plaintext_hex) {
    std::ofstream out("test_in.txt");
    if (!out) {
        return false;
    }
    out << key_hex << '\n' << iv_hex << '\n' << plaintext_hex << '\n';
    return true;
}

bool run_case(const std::string& name, size_t bytes_per_run, int iterations) {
    std::cout << "Benchmark: " << name << '\n';
    std::cout << "  Stream size : " << bytes_per_run << " bytes (" << bytes_per_run * 8 << " bits)\n";
    std::cout << "  Iterations  : " << iterations << '\n';

    const std::string key_hex = random_hex(16);
    const std::string iv_hex = random_hex(16);
    const std::string plaintext_hex = random_hex(bytes_per_run);
    if (!write_aes_input(key_hex, iv_hex, plaintext_hex)) {
        std::cerr << "Failed to write test_in.txt\n";
        return false;
    }

    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) {
        const int ret = std::system("./custom_aes");
        if (ret != 0) {
            std::cerr << "Failed to execute ./custom_aes\n";
            return false;
        }
    }
    auto end = std::chrono::high_resolution_clock::now();

    const std::chrono::duration<double> elapsed = end - start;
    const double total_bits = static_cast<double>(bytes_per_run) * 8.0 * iterations;
    const double mbps = (total_bits / 1000000.0) / elapsed.count();

    std::cout << "  Total time  : " << std::fixed << std::setprecision(4) << elapsed.count() << " s\n";
    std::cout << "  Throughput  : " << std::fixed << std::setprecision(2) << mbps << " Mbps\n";
    if (mbps >= kMinMbps) {
        std::cout << "  Verdict     : PASS (>= 100 Mbps)\n";
    } else {
        std::cout << "  Verdict     : FAIL (< 100 Mbps)\n";
    }
    std::cout << std::string(60, '-') << '\n';
    return true;
}

}  // namespace

int main() {
    std::srand(static_cast<unsigned int>(std::time(nullptr)));

    if (!run_case("8 Kbits stream", kSize8KBitsBytes, kIterations8K)) {
        return 1;
    }
    if (!run_case("8 Mbits stream", kSize8MBitsBytes, kIterations8M)) {
        return 1;
    }
    return 0;
}
