#include "testlib.h"
#include <vector>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (Input)
    int N = inf.readInt();
    int M = inf.readInt();

    // 存储边列表，用于验证独立性约束
    vector<pair<int, int>> edges;
    edges.reserve(M);
    for (int i = 0; i < M; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        edges.push_back({u, v});
    }

    // 2. 读取标准答案 (Answer)
    // ans 文件中只包含一个整数 K* (最优/参考解的大小)
    int K_optimal = ans.readInt();

    // 3. 读取选手输出 (Output) 并统计 K
    vector<int> user_sol(N + 1); // 1-based indexing
    int K_user = 0;

    for (int i = 1; i <= N; i++) {
        // 读取 0 或 1
        int val = ouf.readInt(0, 1, format("x_%d", i)); 
        user_sol[i] = val;
        if (val == 1) {
            K_user++;
        }
    }

    // 4. 验证选手的解是否有效 (Validity Check)
    // 独立集定义：选出的点集中，任意两点之间不能有边
    // 也就是说，对于图中任意一条边 (u, v)，不能同时有 user_sol[u] == 1 和 user_sol[v] == 1
    for (int i = 0; i < M; i++) {
        int u = edges[i].first;
        int v = edges[i].second;

        // 如果一条边的两个端点都被选中了，这就不是独立集
        if (user_sol[u] == 1 && user_sol[v] == 1) {
            quitf(_wa, "Invalid Independent Set: Edge %d-%d has both endpoints selected.", u, v);
        }
    }

    // 5. 计算得分 (Scoring)
    // 最大化问题：分数 = (用户解 / 最优解) * 100
    
    if (K_optimal == 0) {
        if (K_user == 0) quitf(_ok, "Ratio: 1");
        else quitf(_wa, "Jury K is 0 but User K > 0, check data/checker logic.");
    }

    double Ratio = (double)(K_user) / (double)(K_optimal);

    // 6. 输出结果
    quitf(_ok, "Valid Independent Set. K_user=%d, K_jury=%d, Ratio: %.4f", K_user, K_optimal, Ratio);

    return 0;
}