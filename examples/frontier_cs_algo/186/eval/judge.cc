#include "testlib.h"
#include <vector>
#include <set>
#include <algorithm>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (Input)
    // -------------------------
    int n = inf.readInt(); // 节点数
    int m = inf.readInt(); // 边数
    
    // 存储边表
    vector<pair<int, int>> edges;
    for (int i = 0; i < m; ++i) {
        int u = inf.readInt();
        int v = inf.readInt();
        edges.push_back({u, v});
    }

    // 2. 读取用户输出 (Output)
    // -------------------------
    // 读取 n 个整数，表示每个点的颜色
    vector<int> colors(n + 1);
    set<int> distinct_colors;
    
    for (int i = 1; i <= n; ++i) {
        colors[i] = ouf.readInt();
        distinct_colors.insert(colors[i]);
    }

    // 3. 验证合法性 (Validation)
    // -------------------------
    for (auto& e : edges) {
        int u = e.first;
        int v = e.second;
        
        // 如果有边相连的两个点颜色相同，判为 Wrong Answer
        if (colors[u] == colors[v]) {
            quitf(_wa, "Invalid coloring: Node %d and Node %d are connected but share color %d.", u, v, colors[u]);
        }
    }

    // 4. 输出结果 (Result)
    // -------------------------
    int k = distinct_colors.size();

    //Optimal Solution:
    int K_optimal = ans.readInt();
    
    // 如果你有标准答案文件 (.ans)，可以在这里读取并对比 k 值
    // 这里我们只作为评估工具，返回 OK 并打印使用的颜色数量
    quitf(_ok, "Valid coloring found. Used %d colors, Optimal: %d, Ratio: %.4f", k, K_optimal, (double)K_optimal/k);
}