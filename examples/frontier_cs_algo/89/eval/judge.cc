#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct DSU {
    int n;
    vector<int> p, r;
    DSU() {}
    DSU(int n): n(n), p(n + 1), r(n + 1, 0) { iota(p.begin(), p.end(), 0); }
    int find(int x){ return p[x] == x ? x : p[x] = find(p[x]); }
    bool unite(int a, int b){
        a = find(a); b = find(b);
        if (a == b) return false;
        if (r[a] < r[b]) swap(a, b);
        p[b] = a;
        if (r[a] == r[b]) r[a]++;
        return true;
    }
};

struct Tree {
    int n, LOG;
    vector<vector<int>> adj;
    vector<int> depth, parent;
    vector<vector<int>> up;
    vector<int> tin, tout;
    int timer;

    Tree() {}
    Tree(int n): n(n) {
        adj.assign(n + 1, {});
        depth.assign(n + 1, 0);
        parent.assign(n + 1, 0);
        timer = 0;
    }

    void addEdge(int u, int v) {
        adj[u].push_back(v);
        adj[v].push_back(u);
    }

    void dfs(int u, int p) {
        tin[u] = ++timer;
        up[0][u] = p;
        for (int k = 1; k < LOG; ++k) up[k][u] = up[k - 1][ up[k - 1][u] ];
        for (int v : adj[u]) if (v != p) {
            parent[v] = u;
            depth[v] = depth[u] + 1;
            dfs(v, u);
        }
        tout[u] = ++timer;
    }

    void build(int root = 1) {
        LOG = 1;
        while ((1 << LOG) <= n) ++LOG;
        up.assign(LOG, vector<int>(n + 1, 0));
        tin.assign(n + 1, 0);
        tout.assign(n + 1, 0);
        depth[root] = 0;
        parent[root] = root;
        timer = 0;
        dfs(root, root);
    }

    bool isAncestor(int u, int v) const {
        return tin[u] <= tin[v] && tout[v] <= tout[u];
    }

    int lca(int a, int b) const {
        if (isAncestor(a, b)) return a;
        if (isAncestor(b, a)) return b;
        int u = a;
        for (int k = LOG - 1; k >= 0; --k) {
            int w = up[k][u];
            if (!isAncestor(w, b)) u = w;
        }
        return up[0][u];
    }

    int kthAncestor(int u, int k) const {
        for (int i = 0; i < LOG && u; ++i) {
            if (k & (1 << i)) u = up[i][u];
        }
        return u;
    }

    int neighborDirFromVtoS(int v, int s) const {
        if (v == s) return -1; // self
        int w = lca(v, s);
        if (w == v) {
            // s in subtree of v: go down from s up to just below v
            int dist = depth[s] - depth[v] - 1;
            int t = kthAncestor(s, dist);
            return t; // child of v on path towards s
        } else {
            // go up from v: next neighbor is parent[v]
            return parent[v];
        }
    }

    int dist(int a, int b) const {
        int w = lca(a, b);
        return depth[a] + depth[b] - 2 * depth[w];
    }
};

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read n from public input and echo to contestant
    int n = inf.readInt();
    println(n);

    // Read hidden tree from .ans: exactly n-1 edges (u, v)
    Tree tree(n);
    DSU dsu(n);
    vector<pair<int,int>> edges;
    edges.reserve(n - 1);
    for (int i = 0; i < n - 1; ++i) {
        int u = ans.readInt();
        int v = ans.readInt();
        if (u < 1 || u > n || v < 1 || v > n || u == v) {
            quitf(_fail, "Secret tree invalid: edge (%d, %d) out of range or self-loop.", u, v);
        }
        edges.emplace_back(u, v);
        tree.addEdge(u, v);
        dsu.unite(u, v);
    }
    // Optional: validate connectivity
    int root_parent = dsu.find(1);
    for (int i = 2; i <= n; ++i) {
        if (dsu.find(i) != root_parent) {
            quitf(_fail, "Secret tree not connected.");
        }
    }

    // Preprocess LCA and parent
    tree.build(1);

    const long long SET_SIZE_LIMIT = 3000000LL; // total sum of k across all queries
    long long total_set_size = 0;
    long long query_count = 0;

    // Interaction loop
    while (true) {
        string op = ouf.readWord();
        if (op == "?") {
            int k = ouf.readInt();
            int v = ouf.readInt();
            if (k < 1 || k > n) {
                quitf(_wa, "Invalid query: k=%d out of range [1..%d].", k, n);
            }
            if (v < 1 || v > n) {
                quitf(_wa, "Invalid query: v=%d out of range [1..%d].", v, n);
            }
            vector<int> S(k);
            unordered_set<int> seenS;
            seenS.reserve(k * 2);
            for (int i = 0; i < k; ++i) {
                S[i] = ouf.readInt();
                if (S[i] < 1 || S[i] > n) {
                    quitf(_wa, "Invalid query: S[%d]=%d out of range [1..%d].", i, S[i], n);
                }
                if (seenS.count(S[i])) {
                    quitf(_wa, "Invalid query: S contains duplicates (value %d).", S[i]);
                }
                seenS.insert(S[i]);
            }

            total_set_size += k;
            if (total_set_size > SET_SIZE_LIMIT) {
                println(-1);
                quitf(_wa, "Exceeded total set size limit (%lld).", SET_SIZE_LIMIT);
            }

            ++query_count;

            int ans_bit = 0;
            if (k == 1) {
                ans_bit = (S[0] == v) ? 1 : 0;
            } else {
                bool self_in = (seenS.count(v) > 0);
                // count distinct neighbor directions from v that contain S
                unordered_set<int> dirs;
                dirs.reserve(min(k, 8)); // small initial reserve
                for (int s : S) {
                    if (s == v) continue;
                    int dir = tree.neighborDirFromVtoS(v, s);
                    dirs.insert(dir);
                    if ((int)dirs.size() + (self_in ? 1 : 0) >= 2) break; // early exit
                }
                int count = (int)dirs.size() + (self_in ? 1 : 0);
                ans_bit = (count >= 2) ? 1 : 0;
            }

            println(ans_bit);
        } else if (op == "!") {
            // contestant outputs final tree: n-1 undirected edges (u v)
            unordered_set<long long> expected; expected.reserve((n - 1) * 2);
            for (auto [u, v] : edges) {
                int a = min(u, v), b = max(u, v);
                long long key = (long long)a << 32 | (unsigned long long)b;
                expected.insert(key);
            }

            unordered_set<long long> got; got.reserve((n - 1) * 2);
            bool ok = true;
            string err;

            for (int i = 0; i < n - 1; ++i) {
                int u = ouf.readInt();
                int v = ouf.readInt();
                if (u < 1 || u > n || v < 1 || v > n || u == v) {
                    ok = false; err = "Answer has invalid edge endpoint or self-loop."; break;
                }
                int a = min(u, v), b = max(u, v);
                long long key = (long long)a << 32 | (unsigned long long)b;
                if (got.count(key)) {
                    ok = false; err = "Answer has duplicate edge."; break;
                }
                got.insert(key);
            }

            if (ok) {
                if ((int)got.size() != (int)expected.size()) {
                    ok = false; err = "Answer edge count mismatch.";
                } else if (got != expected) {
                    ok = false; err = "Answer edges mismatch the hidden tree.";
                }
            }

            if (!ok) {
                quitf(_wa, "%s", err.c_str());
            } else {
                // Scoring based on number of queries Q
                // Full score if Q <= 3000, zero if Q > 1,200,000, otherwise linear interpolation.
                const long long Q_full = 3000;
                const long long Q_zero = 1200000;
                double ratio = 0.0, unbounded_ratio = 0.0;
                if (query_count <= Q_full) ratio = 1.0, unbounded_ratio = 1.0;
                else if (query_count > Q_zero) ratio = 0.0;
                else {
                    ratio = double(Q_zero - query_count) / double(Q_zero - Q_full);
                    if (ratio < 0.0) ratio = 0.0;
                    unbounded_ratio = max(0.0, ratio);
                    if (ratio > 1.0) ratio = 1.0;
                }
                quitp(ratio, "Ratio: %.4f, RatioUnbounded: %.4f.", ratio, unbounded_ratio);
            }

            break;
        } else {
            quitf(_wa, "Invalid operation: expected '?' or '!', got '%s'.", op.c_str());
        }
    }

    return 0;
}