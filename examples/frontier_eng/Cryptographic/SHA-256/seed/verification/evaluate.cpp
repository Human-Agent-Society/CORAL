#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace {

constexpr size_t kSize8KBitsBytes = 1000;
constexpr size_t kSize8MBitsBytes = 1000000;
constexpr int kIterations8K = 500;
constexpr int kIterations8M = 50;
constexpr double kMinMbps = 100.0;

bool generate_test_file(const std::string& filename, size_t size_in_bytes) {
    std::ofstream out(filename, std::ios::binary);
    if (!out) {
        return false;
    }

    std::vector<char> buffer(4096);
    for (char& value : buffer) {
        value = static_cast<char>(std::rand() % 256);
    }

    size_t written = 0;
    while (written < size_in_bytes) {
        const size_t chunk = std::min(buffer.size(), size_in_bytes - written);
        out.write(buffer.data(), static_cast<std::streamsize>(chunk));
        written += chunk;
    }
    return true;
}

bool run_case(const std::string& name,
              const std::string& input_file,
              size_t bytes_per_run,
              int iterations) {
#ifdef _WIN32
    const std::string command = "custom_sha.exe < " + input_file + " > NUL";
#else
    const std::string command = "./custom_sha < " + input_file + " > /dev/null";
#endif

    std::cout << "Benchmark: " << name << '\n';
    std::cout << "  Stream size : " << bytes_per_run << " bytes (" << bytes_per_run * 8 << " bits)\n";
    std::cout << "  Iterations  : " << iterations << '\n';

    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) {
        const int ret = std::system(command.c_str());
        if (ret != 0) {
            std::cerr << "Failed to execute custom_sha\n";
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

    const std::string file_8kbits = "test_8kbits.bin";
    const std::string file_8mbits = "test_8mbits.bin";

    if (!generate_test_file(file_8kbits, kSize8KBitsBytes) ||
        !generate_test_file(file_8mbits, kSize8MBitsBytes)) {
        std::cerr << "Failed to generate test files\n";
        return 1;
    }

    bool ok = true;
    ok = ok && run_case("8 Kbits stream", file_8kbits, kSize8KBitsBytes, kIterations8K);
    ok = ok && run_case("8 Mbits stream", file_8mbits, kSize8MBitsBytes, kIterations8M);

    std::remove(file_8kbits.c_str());
    std::remove(file_8mbits.c_str());
    return ok ? 0 : 1;
}
