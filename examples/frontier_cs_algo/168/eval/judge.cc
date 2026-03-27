#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    int N = inf.readInt();
    int M = inf.readInt();
    long long H = inf.readLong();

    vector<long long> A(N);
    for (int i = 0; i < N; i++) A[i] = inf.readLong();

    vector<pair<int,int>> edges;
    edges.reserve(M);
    for (int i = 0; i < M; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        if (u > v) swap(u, v);
        edges.emplace_back(u, v);
    }
    sort(edges.begin(), edges.end());

    // Read points (not used in scoring, read to consume input)
    for (int i = 0; i < N; i++) {
        (void)inf.readLong();
        (void)inf.readLong();
    }

    // Read participant output: possibly multiple solutions; use the last one.
    vector<int> parents;
    bool hasAny = false;
    while (!ouf.seekEof()) {
        vector<int> cur(N);
        for (int i = 0; i < N; i++) {
            cur[i] = ouf.readInt(-1, N - 1);
        }
        parents.swap(cur);
        hasAny = true;
    }
    if (!hasAny) {
        quitf(_wa, "empty output");
    }

    // Check edges exist and build forest
    auto contains_edge = [&](int u, int v) -> bool {
        if (u > v) swap(u, v);
        return binary_search(edges.begin(), edges.end(), make_pair(u, v));
    };

    vector<vector<int>> children(N);
    vector<int> indeg(N, 0);
    for (int v = 0; v < N; v++) {
        int p = parents[v];
        if (p == -1) continue;
        if (!contains_edge(v, p)) {
            quitf(_wa, "Edge (%d, %d) is not included in the original graph.", v, p);
        }
        indeg[v] += 1;
        children[p].push_back(v);
    }

    // BFS from roots (indegree 0)
    vector<long long> depth(N, -1);
    vector<int> root(N, -1);
    queue<int> q;
    for (int v = 0; v < N; v++) {
        if (indeg[v] == 0) {
            depth[v] = 0;
            root[v] = v;
            q.push(v);
        }
    }
    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int w : children[u]) {
            if (depth[w] != -1) continue; // already visited
            depth[w] = depth[u] + 1;
            root[w] = root[u];
            q.push(w);
        }
    }

    // Validate all vertices are covered by rooted trees
    for (int v = 0; v < N; v++) {
        if (depth[v] == -1) {
            quitf(_wa, "The connected component that contains vertex %d is not a rooted tree.", v);
        }
    }

    // Height constraint
    for (int v = 0; v < N; v++) {
        if (depth[v] > H) {
            quitf(_wa, "Vertex %d is too high (h = %lld).", v, depth[v]);
        }
    }

    // Compute score
    long long score = 1;
    for (int v = 0; v < N; v++) {
        score += A[v] * (depth[v] + 1);
    }

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}