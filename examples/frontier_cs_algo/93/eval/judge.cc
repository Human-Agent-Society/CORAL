#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

/*
Interactor for "Greedy" (revised, Standard I/O)

Input/Output (to contestant):
- First, send: "n ty\n"
- Then answer queries of the form:
    Contestant -> Interactor: "? sz v1 v2 ... vsz"
    Interactor -> Contestant: R   (greedy result size)
- Final answer:
    Contestant -> Interactor: "! p1 p2 ... pn"
    Interactor finishes with verdict via quitp/quitf.

Files:
- .in  (visible):  n ty
- .ans (hidden):   p1 p2 ... pn   (parent array, 1-indexed; exactly one 0 = root)
*/

static const int MAX_QUERIES_HARD = 1000000; // hard safety cap

struct Tree {
    int n;
    int root;
    vector<int> par;
    vector<vector<int>> g;
    vector<int> tin, tout;
    int timer = 0;

    void dfs(int u) {
        tin[u] = ++timer;
        for (int v : g[u]) dfs(v);
        tout[u] = ++timer;
    }
    void buildTinTout() {
        tin.assign(n + 1, 0);
        tout.assign(n + 1, 0);
        timer = 0;
        dfs(root);
    }
};

int greedyResult(const vector<int>& vec, const Tree& T) {
    // Maintain selected nodes as an antichain, keyed by tin
    struct Item { int tin, node; };
    struct Cmp {
        bool operator()(const Item& a, const Item& b) const {
            if (a.tin != b.tin) return a.tin < b.tin;
            return a.node < b.node;
        }
    };
    std::set<Item, Cmp> S;

    int accepted = 0;
    for (int x : vec) {
        Item key{T.tin[x], x};
        auto it = S.lower_bound(key);

        // Check predecessor: if its tout > tin[x], it contains x (ancestor)
        if (it != S.begin()) {
            auto pit = prev(it);
            int y = pit->node;
            if (T.tout[y] > T.tin[x]) {
                continue; // reject x
            }
        }
        // Check successor: if its tin < tout[x], x contains it (descendant)
        if (it != S.end()) {
            int y = it->node;
            if (T.tin[y] < T.tout[x]) {
                continue; // reject x
            }
        }
        // Otherwise, accept x
        S.insert({T.tin[x], x});
        accepted++;
    }
    return accepted;
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read public from .in
    int n = inf.readInt(1, 3000, "n");
    int ty = inf.readInt(0, 1000000000, "ty"); // ty is a test identifier for contestants to ignore

    // Read hidden answer: parent array p1..pn (1-indexed), exactly one 0 (root)
    Tree T;
    T.n = n;
    T.par.assign(n + 1, -1);
    int rootCount = 0;
    for (int i = 1; i <= n; ++i) {
        int p = ans.readInt(-1000000000, 1000000000, "par[i]");
        T.par[i] = p;
        if (p == 0) rootCount++;
    }
    if (rootCount != 1) {
        quitf(_fail, "Answer file invalid: expected exactly one root (par[i]=0), found %d.", rootCount);
    }
    // Build tree, detect root
    T.g.assign(n + 1, {});
    T.root = -1;
    for (int i = 1; i <= n; ++i) {
        int p = T.par[i];
        if (p == 0) {
            if (T.root != -1) {
                quitf(_fail, "Answer file invalid: multiple roots (nodes %d and %d).", T.root, i);
            }
            T.root = i;
        } else {
            if (p < 1 || p > n) {
                quitf(_fail, "Answer file invalid: par[%d]=%d out of range [0..%d].", i, p, n);
            }
            T.g[p].push_back(i);
        }
    }
    if (T.root == -1) {
        quitf(_fail, "Answer file invalid: no root (no par[i]=0).");
    }
    // Verify edge count
    int edges = 0;
    for (int u = 1; u <= n; ++u) edges += (int)T.g[u].size();
    if (edges != n - 1) {
        quitf(_fail, "Answer file invalid: expected n-1 edges (%d), found %d.", n - 1, edges);
    }

    // Preprocess tin/tout for ancestor checks
    T.buildTinTout();

    // Send public n and ty to contestant
    println(std::to_string(n) + " " + std::to_string(ty));

    long long query_count = 0;

    while (true) {
        if (query_count > MAX_QUERIES_HARD) {
            quitp(0.0, "Query limit exceeded. Max queries: %d. Ratio: 0.0000", MAX_QUERIES_HARD);
        }

        // Read action token: must be "?" or "!"
        // FIX: pattern must accept '?' or '!' instead of the literal "action"
        string action = ouf.readToken("[!?]", "action");

        if (action == "?") {
            query_count++;

            int sz = ouf.readInt(1, n, "sz");

            vector<int> vec(sz);
            vector<char> seen(n + 1, 0);
            for (int i = 0; i < sz; ++i) {
                int v = ouf.readInt(1, n, "v");
                if (seen[v]) {
                    quitf(_wa, "Invalid query: duplicate element %d.", v);
                }
                seen[v] = 1;
                vec[i] = v;
            }

            // Compute greedy result
            int res = greedyResult(vec, T);
            println(res);

        } else if (action == "!") {
            // Final parent array
            vector<int> guess(n + 1, -1);
            int rootSeen = 0;
            for (int i = 1; i <= n; ++i) {
                int p = ouf.readInt(-1000000000, 1000000000, "par[i]");
                if (p == 0) rootSeen++;
                if (p < 0 || p > n) {
                    quitf(_wa, "Invalid final answer: par[%d]=%d out of range [0..%d].", i, p, n);
                }
                guess[i] = p;
            }
            if (rootSeen != 1) {
                quitf(_wa, "Invalid final answer: expected exactly one root (par[i]=0), found %d.", rootSeen);
            }

            // Check correctness
            bool ok = true;
            for (int i = 1; i <= n; ++i) {
                if (guess[i] != T.par[i]) { ok = false; break; }
            }

            if (!ok) {
                quitp(0.0, "Wrong reconstruction. Ratio: 0.0000");
            } else {
                // Map query count to ratio per problem's 0–100 scale
                double ratio, unbounded_ratio;
                if (query_count >= 200000) ratio = 0.0;
                else ratio = (200000.0 - (double)query_count) / 155000.0;
                
                unbounded_ratio = max(0.0, ratio);
                ratio = max(0.0, min(1.0, ratio));

                quitp(ratio, "Correct reconstruction in %lld queries. Ratio: %.4f, RatioUnbounded: %.4f",
                      query_count, ratio, unbounded_ratio);
            }
            break;

        } else {
            quitf(_wa, "Invalid action token: expected '?' or '!', got '%s'.", action.c_str());
        }
    }

    return 0;
}
