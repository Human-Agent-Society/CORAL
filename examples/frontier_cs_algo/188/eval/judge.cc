#include "testlib.h"
#include <string>
#include <vector>

using namespace std;

// 贪心验证 subsequence (O(N))
bool is_subsequence(const string& text, const string& pattern) {
    if (pattern.empty()) return true;
    int p_idx = 0;
    int p_len = pattern.length();
    
    for (char c : text) {
        if (c == pattern[p_idx]) {
            p_idx++;
            if (p_idx == p_len) return true;
        }
    }
    return false;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // 1. 读取输入
    string s1 = inf.readLine();
    string s2 = inf.readLine();

    // 2. 读取标准答案 (Generator 生成到 stderr 并重定向到了 answer file)
    // ans 对象读取 .ans 文件
    string z_opt = ans.readString(); 
    double len_opt = (double)z_opt.length();

    // 3. 读取选手输出
    string z_user = ouf.readLine();
    double len_user = (double)z_user.length();

    // 4. 验证选手合法性
    if (!is_subsequence(s1, z_user)) {
        quitf(_wa, "Output is not a subsequence of S1. First mismatch logic check failed.");
    }
    if (!is_subsequence(s2, z_user)) {
        quitf(_wa, "Output is not a subsequence of S2.");
    }

    // 5. 计算分数
    if (len_opt == 0) len_opt = 1; // 防止除零，虽然不可能
    double score = (len_user / len_opt);
    
    // 限制最高分显示（因为选手可能找到比我们预设更好的解，虽然对于 trap 数据很难）
    // 如果选手比 answer 还要好，允许超过 100 分，或者截断
    // 既然是 heuristic 比赛，通常显示实际百分比
    
    string message = format("User: %.0f, Opt: %.0f, Ratio: %.4f%%", len_user, len_opt, score);

    // 这里使用 _ok 并带上分数，或者使用 _points (如果是部分分模式)
    // Codeforces 风格通常只给 AC/WA，但在 heuristic 比赛中，checker 需要返回分数
    // 如果是在本地测试或 Polygon，通常输出 score 到 stdout 或 stderr
    
    quitf(_ok, "%s", message.c_str());
}