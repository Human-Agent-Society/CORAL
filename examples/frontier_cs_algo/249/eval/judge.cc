#include "testlib.h"
#include <vector>
#include <iostream>
#include <cmath>
#include <algorithm>
#include <string>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib 环境
    setName("Interactor for X-OR (CF 1364E) with Dynamic Scoring");
    registerInteraction(argc, argv);

    // 统计变量
    double total_score = 0.0;
    long long tot_moves = 0;
    double tot_unbounded_score = 0.0;
    
    // 假设当前输入文件只包含 1 个 test case (根据之前的 python script 格式)
    // 如果题目格式变成第一行是 T (test case 数量)，可以改为: int t = inf.readInt(); while(t--)
    int n_graphs = 1; 

    for (int g = 0; g < n_graphs; ++g) {
        // --- 读取当前 Test Case 数据 ---
        int n = inf.readInt(3, 2048, "n");
        vector<int> p(n);
        for (int i = 0; i < n; ++i) {
            p[i] = inf.readInt(0, n - 1, "p_i");
        }

        // --- 动态计算评分阈值 ---
        // 逻辑：
        // Base (满分线): 约为 N + 常数 (高效解法通常需要 N + logN 或 N + const 次)
        // Zero (零分线): 约为 2N + 常数 (暴力解法或低效解法)
        // 参考原题 N=2048 时 Base=2100, Zero=4300
        long long current_k_base = 2 * n + 2 * log2(n);
        long long current_k_zero = n * n;

        // 发送 N 给用户
        cout << n << endl;

        // --- 交互循环 ---
        int queries = 0;
        bool solved = false;
        
        // 硬性上限，防止死循环，设定为 Zero 阈值的一定倍数
        int hard_limit = current_k_zero + 200; 

        while (true) {
            string type = ouf.readToken("[?!]");
            
            if (type == "?") {
                queries++;
                
                int i = ouf.readInt(1, n, "i");
                int j = ouf.readInt(1, n, "j");
                
                if (i == j) {
                    // 严重错误直接判 WA
                    quitf(_wa, "Invalid query: indices i (%d) and j (%d) must be distinct", i, j);
                }

                int val = p[i-1] | p[j-1];
                cout << val << endl;

                // 检查是否严重超出限制 (可选)
                if (queries > hard_limit) {
                    // 这里不直接 quitf，允许用户继续直到一定程度，
                    // 但分数会在后面被计算为 0
                }
            } 
            else if (type == "!") {
                vector<int> user_p(n);
                for(int k=0; k<n; ++k) {
                    user_p[k] = ouf.readInt(0, n - 1, "ans_val");
                }
                
                if (user_p == p) {
                    solved = true;
                } else {
                    quitf(_wa, "Incorrect permutation guessed for n=%d.", n);
                }
                break; 
            }
        }

        tot_moves += queries;

        // --- 计算当前 Case 分数 ---
        // Formula: Score = max(0, 100 * ((K_zero - Q) / (K_zero - K_base))^2)
        
        double case_score = 0.0;
        double unbounded_case_score = 0.0;
        
        double denom = (double)(current_k_zero - current_k_base);
        double num = (double)(current_k_zero - queries);
        
        // 计算原始比例的平方
        double raw_ratio = num / denom;
        double raw_score_val = raw_ratio * raw_ratio;

        if (solved) {
            // Unbounded Score (允许超过 100 分，也允许低分但不强制截断为0，除非 num < 0)
            if (num < 0) {
                 // 如果超过 K_ZERO，Unbounded 通常也视为 0 或非常低，这里保持逻辑一致性设为 0
                 unbounded_case_score = 0.0;
            } else {
                 unbounded_case_score = raw_score_val;
            }

            // Official Score (Clamped 0.0 - 1.0 based on logic, represented as ratio here)
            if (queries >= current_k_zero) {
                case_score = 0.0;
            } else if (queries <= current_k_base) {
                case_score = 1.0; // 满分 (即 100pts)
            } else {
                case_score = raw_score_val;
            }
        } else {
            case_score = 0.0;
            unbounded_case_score = 0.0;
        }

        total_score += case_score;
        tot_unbounded_score += unbounded_case_score;
    }

    // --- 最终判定 ---
    // 计算平均分
    double score_ratio = total_score / (double)n_graphs;
    double unbounded_score_ratio = tot_unbounded_score / (double)n_graphs;

    // 输出必须完全照抄给出的例子
    quitp(score_ratio, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", tot_moves, score_ratio, unbounded_score_ratio);

    return 0;
}