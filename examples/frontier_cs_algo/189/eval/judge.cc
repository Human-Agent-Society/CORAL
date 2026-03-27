#include "testlib.h"
#include <string>
#include <algorithm>
#include <vector>
#include <cmath>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (S1, S2)
    string s1 = inf.readToken();
    string s2 = inf.readToken();

    int n = s1.length();
    int m = s2.length();

    // 2. 读取用户输出 (Transcript)
    string t = ouf.readToken();

    // 3. 验证 Transcript 并计算用户的 LCS 长度
    int i = 0; // S1 指针
    int j = 0; // S2 指针
    
    // 变更点：这里不再累计距离，而是累计匹配长度 (LCS)
    int user_lcs = 0; 

    for (size_t k = 0; k < t.length(); k++) {
        char op = t[k];

        if (op == 'M') {
            // Match/Substitute: 消耗 S1 和 S2 各一个字符
            if (i >= n) quitf(_wa, "Invalid transcript: Transcript tries to match but S1 is exhausted at index %d.", i);
            if (j >= m) quitf(_wa, "Invalid transcript: Transcript tries to match but S2 is exhausted at index %d.", j);
            
            // 变更点：只有当字符真正相等时，LCS 长度才 +1
            // 如果 op 是 'M' 但字符不相等，这在编辑距离中是 Substitute，在 LCS 中不算贡献
            if (s1[i] == s2[j]) {
                user_lcs++; 
            }
            
            i++;
            j++;
        } 
        else if (op == 'D') {
            // Delete: 消耗 S1 一个字符，不贡献 LCS
            if (i >= n) quitf(_wa, "Invalid transcript: Transcript tries to delete but S1 is exhausted at index %d.", i);
            i++;
        } 
        else if (op == 'I') {
            // Insert: 消耗 S2 一个字符，不贡献 LCS
            if (j >= m) quitf(_wa, "Invalid transcript: Transcript tries to insert but S2 is exhausted at index %d.", j);
            j++;
        } 
        else {
            quitf(_wa, "Invalid character '%c' in transcript. Only 'M', 'D', 'I' are allowed.", op);
        }
    }

    // 4. 检查是否完全消耗了 S1 和 S2
    if (i != n) {
        quitf(_wa, "Invalid transcript: S1 was not fully consumed. Ended at %d/%d.", i, n);
    }
    if (j != m) {
        quitf(_wa, "Invalid transcript: S2 was not fully consumed. Ended at %d/%d.", j, m);
    }

    // 5. 读取标准答案中的最优 LCS 长度
    // 变更点：现在 .ans 文件里存的是 LCS 的长度
    int optimal_lcs = ans.readInt();

    // 6. 计算分数
    // 变更点：分数基于 LCS 的比例
    double score = 0.0;

    if (optimal_lcs == 0) {
        // 如果最优 LCS 是 0 (两个字符串完全没有公共字符)
        // 只要用户也没匹配到任何字符，就是满分
        if (user_lcs == 0) score = 100.0;
        else score = 0.0; // 理论上不可能发生 user_lcs > 0 而 optimal_lcs == 0
    } else {
        // 你的得分公式：(用户找到的LCS / 理论最优LCS) * 100
        score = 100.0 * (double)user_lcs / (double)optimal_lcs;
    }

    // 7. 处理边界情况
    if (score < 0.0) score = 0.0;
    
    // 如果用户算出的 LCS 比裁判给的还大（说明裁判数据弱了，或者是错的），限制为 100 分
    // 也可以选择 fail 掉 judge，但在比赛中通常给满分
    if (user_lcs > optimal_lcs) {
        score = 100.0;
    }
    
    if (score > 100.0) score = 100.0;

    // 8. 输出结果 (Partial Score)
    quitf(_ok, "User LCS: %d, Optimal LCS: %d. Ratio: %.4f", user_lcs, optimal_lcs, (double) (score / 100.0));

    return 0;
}