#include "testlib.h"
#include <vector>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (Input)
    int N = inf.readInt();
    int M = inf.readInt();

    // 存储边列表
    vector<pair<int, int>> edges;
    edges.reserve(M);
    for (int i = 0; i < M; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        edges.push_back({u, v});
    }

    // 2. 读取标准答案 (Answer)
    // ans 文件中只包含一个整数 K*（最大团大小）
    int K_optimal = ans.readInt();

    // 3. 读取选手输出 (Output)
    vector<int> user_sol(N + 1); // 1-based
    int K_user = 0;

    for (int i = 1; i <= N; i++) {
        int val = ouf.readInt(0, 1, format("x_%d", i));
        user_sol[i] = val;
        if (val == 1) {
            K_user++;
        }
    }

    // 4. 验证选手解是否合法 (Clique Validity Check)
    // Clique 定义：
    // 对任意 u != v，只要 user_sol[u] == 1 且 user_sol[v] == 1，
    // 就必须存在边 (u, v)

    // 先构建邻接矩阵（用 char 即可，节省内存）
    vector<vector<char>> adj(N + 1, vector<char>(N + 1, 0));
    for (auto &e : edges) {
        int u = e.first;
        int v = e.second;
        if (u != v) {
            adj[u][v] = 1;
            adj[v][u] = 1;
        }
    }

    // 检查所有被选中的点对
    for (int u = 1; u <= N; u++) {
        if (!user_sol[u]) continue;
        for (int v = u + 1; v <= N; v++) {
            if (!user_sol[v]) continue;
            if (!adj[u][v]) {
                quitf(_wa,
                      "Invalid Clique: vertices %d and %d are both selected but no edge exists.",
                      u, v);
            }
        }
    }

    // 5. 计算得分 (Scoring)
    // Score = (K_user / K_optimal) * 100

    if (K_optimal == 0) {
        if (K_user == 0) {
            quitf(_ok, "Ratio: 1");
        } else {
            quitf(_wa, "Jury K is 0 but User K > 0, check data/checker logic.");
        }
    }

    double Ratio = (double)(K_user) / (double)(K_optimal);

    // 6. 输出结果
    quitf(_ok,
          "Valid Clique. K_user=%d, K_jury=%d, Ratio: %.4f",
          K_user, K_optimal, Ratio);

    return 0;
}
