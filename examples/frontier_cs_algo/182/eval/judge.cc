#include "testlib.h"
#include <vector>

using namespace std;

int main(int argc, char* argv[]) {
    // 初始化 testlib
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (Input)
    int N = inf.readInt();
    int M = inf.readInt();

    // 存储边列表，用于验证覆盖
    vector<pair<int, int>> edges;
    edges.reserve(M);
    for (int i = 0; i < M; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        edges.push_back({u, v});
    }

    // 2. 读取标准答案 (Answer)
    // 修改处：ans 文件中只包含一个整数 K* (最优/参考解的大小)
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
    for (int i = 0; i < M; i++) {
        int u = edges[i].first;
        int v = edges[i].second;

        // 如果一条边的两个端点都没被选中
        if (user_sol[u] == 0 && user_sol[v] == 0) {
            quitf(_wa, "Edge %d-%d is not covered (vertices %d and %d are both 0).", u, v, u, v);
        }
    }

    // 5. 计算得分 (Scoring)
    if (K_user == 0) {
        if (M == 0) {
             quitf(_ok, "Ratio: 1");
        } else {
             quitf(_wa, "Logic error: Valid solution found with size 0 for non-empty graph.");
        }
    }

    double score = (double)K_optimal / K_user * 100.0;
    double Ratio = (double)K_optimal / K_user;

    // 6. 输出结果
    quitf(_ok, "Valid Vertex Cover. K_user=%d, K_jury=%d, Ratio: %.4f", K_user, K_optimal, Ratio);

    return 0;
}