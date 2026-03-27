#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct PairHash {
    size_t operator()(const pair<int,int>& p) const noexcept {
        return (size_t)p.first * 1000003u ^ (size_t)p.second;
    }
};

struct Tree {
    int n, LOG;
    vector<vector<pair<int,int>>> adj; // (to, w)
    vector<int> depth;
    vector<long long> dist;
    vector<vector<int>> up; // up[k][v]
    vector<bool> visited;

    Tree() {}
    Tree(int n): n(n) {
        adj.assign(n + 1, {});
    }

    void addEdge(int u, int v, int w) {
        adj[u].push_back({v, w});
        adj[v].push_back({u, w});
    }

    void build(int root = 1) {
        depth.assign(n + 1, 0);
        dist.assign(n + 1, 0);
        visited.assign(n + 1, false);
        LOG = 1;
        while ((1ll << LOG) <= n) ++LOG;
        up.assign(LOG, vector<int>(n + 1, 0));

        // BFS to set parent (up[0]), depth, dist
        queue<int> q;
        vector<int> parent(n + 1, 0);
        parent[root] = root;
        up[0][root] = root;
        depth[root] = 0;
        dist[root] = 0;
        visited[root] = true;
        q.push(root);
        while (!q.empty()) {
            int u = q.front(); q.pop();
            visited[u] = true;
            for (auto [v, w] : adj[u]) {
                if (v == parent[u] || visited[v]) continue;
                parent[v] = u;
                up[0][v] = u;
                depth[v] = depth[u] + 1;
                dist[v] = dist[u] + w;
                visited[v] = true;
                q.push(v);
            }
        }

        for (int k = 1; k < LOG; ++k) {
            for (int v = 1; v <= n; ++v) {
                up[k][v] = up[k - 1][ up[k - 1][v] ];
            }
        }
    }

    int lca(int a, int b) const {
        if (depth[a] < depth[b]) swap(a, b);
        int diff = depth[a] - depth[b];
        for (int k = LOG - 1; k >= 0; --k) {
            if ((diff >> k) & 1) a = up[k][a];
        }
        if (a == b) return a;
        for (int k = LOG - 1; k >= 0; --k) {
            if (up[k][a] != up[k][b]) {
                a = up[k][a];
                b = up[k][b];
            }
        }
        return up[0][a];
    }

    long long distance(int u, int v) const {
        int w = lca(u, v);
        return dist[u] + dist[v] - 2LL * dist[w];
    }

    ~Tree(){
        adj.clear();
        depth.clear();
        dist.clear();
        up.clear();
    }

};

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    double score = 1.0;

    // case1: quitp(score, "Correct. Ratio: %.4f", score);
    // case2: quitp(score, "score ratio: %.4f.", score);

    // Read public data
    int T = inf.readInt(); // number of test cases
    println(T); // Echo to player

    double final_ratio = 0;


    // Score accumulation: average by group
    double total_ratio = 0.0;
    double total_unbounded_ratio = 0.0;
    bool flag_error = false;

    for (int tc = 1; tc <= T; ++tc) {
        int n = inf.readInt();
        println(n); // Echo to player

        // Read hidden tree from .ans (non-adaptive)
        Tree tree(n);
        // For fast answer verification, prepare expectedEdges: key=(min(u,v), max(u,v)) -> w
        unordered_map<pair<int,int>, int, PairHash> expectedEdges;
        // expectedEdges.reserve((size_t).(n * 2));

        for (int i = 0; i < n - 1; ++i) {
            int u = ans.readInt();
            int v = ans.readInt();
            int w = ans.readInt();
            // if (u < 1 || u > n || v < 1 || v > n || u == v) {
            //     quitf(_fail, "Secret tree invalid at test %d: edge (%d, %d, %d) out of range.", tc, u, v, w);
            // }
            // if (w < 1 || w > 10000) {
            //     quitf(_fail, "Secret edge weight out of range at test %d: w=%d.", tc, w);
            // }
            int a = min(u, v), b = max(u, v);
            auto key = make_pair(a, b);
            // if (expectedEdges.count(key)) {
            //     quitf(_fail, "Secret tree has duplicate edge at test %d: (%d, %d).", tc, a, b);
            // }
            expectedEdges[key] = w;
            tree.addEdge(u, v, w);
        }

        // Preprocess to answer distance queries in O(log n)
        tree.build(1);

        long long query_count = 0;
        long long limit_queries = n * (n + 1) / 2;

        // Interaction for this group
        while (query_count <= limit_queries) {
            string op = ouf.readWord();
            if (op == "?") {
                int u = ouf.readInt();
                int v = ouf.readInt();
                if (u < 1 || u > n || v < 1 || v > n || u == v) {
                    quitf(_wa, "Invalid query at test %d: u=%d, v=%d (must be 1..%d and u!=v).", tc, u, v, n);
                }
                ++query_count;
                long long d = tree.distance(u, v);
                println(d);
            } else if (op == "!") {
                // Read player's answer: 3*(n-1) integers
                unordered_set<pair<int,int>, PairHash> seen;
                // seen.reserve((size_t)(n * 2));
                bool ok = true;
                string err = "";

                for (int i = 0; i < n - 1; ++i) {
                    int u = ouf.readInt();
                    int v = ouf.readInt();
                    int w = ouf.readInt();

                    if (u < 1 || u > n || v < 1 || v > n || u == v) {
                        ok = false;
                        err = "Answer has invalid edge endpoint.";
                    }
                    if (!ok) continue;
                    int a = min(u, v), b = max(u, v);
                    auto key = make_pair(a, b);
                    if (seen.count(key)) {
                        ok = false;
                        err = "Answer has duplicate edge.";
                        continue;
                    }
                    seen.insert(key);
                    auto it = expectedEdges.find(key);
                    if (it == expectedEdges.end()) {
                        ok = false;
                        err = "Answer contains non-existing edge.";
                        continue;
                    }
                    if (it->second != w) {
                        ok = false;
                        err = "Answer edge weight mismatch.";
                        continue;
                    }
                }

                // If count is wrong or not connected, seen.size() != n-1 will trigger above logic,
                // Complete edge and weight match means consistent with hidden tree.
                if (!ok) {
                    // Score 0 for this group, continue to next
                    flag_error = true;
                    total_ratio += 0.0;
                    quitf(_wa, "Error is test %d: %s", tc, err.c_str());
                } else {
                    // Calculate score for this group (ratio in [0,1])
                    // - q <= 5n: ratio = 1
                    // - q >= n^2 / 3: ratio = 0
                    // - Linear interpolation
                    long long q = query_count;
                    long long full_thr = 5LL * n;
                    long long zero_thr = (long long)n * (long long)n / 3LL;
                    double raw_ratio = 0.0;
                    if (zero_thr <= full_thr) {
                        raw_ratio = (q <= full_thr) ? 1.0 : 0.0;
                    } else {
                        double denom = (double)(zero_thr - full_thr);
                        raw_ratio = 1.0 - (double)(q - full_thr) / denom;
                    }
                    double ratio = std::min(1.0, std::max(0.0, raw_ratio));
                    double unbounded_ratio = std::max(0.0, raw_ratio);
                    total_ratio += ratio;
                    total_unbounded_ratio += unbounded_ratio;
                }

                // Move to next group
                break;
            } else {
                quitf(_wa, "Invalid operation at test %d: expected '?' or '!', got '%s'.", tc, op.c_str());
            }
        }
    }

    final_ratio = flag_error ? 0 : total_ratio / (double)T;
    double final_unbounded_ratio = flag_error ? 0 : total_unbounded_ratio / (double)T;
    long long score_value = llround(final_unbounded_ratio * 10000.0);
    // Output score ratio [0,1] with human-readable info (not sent to player, only for judge log)
    quitp(final_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score_value, final_ratio, final_unbounded_ratio);

    return 0;
}
