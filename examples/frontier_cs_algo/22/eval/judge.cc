#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // read input (problem instance)
    int N = inf.readInt(4, 100000, "N");

    // original tree edges: input gives p_i for i=1..N-1 meaning edge (p_i, i+1), 1 <= p_i <= i
    vector<pair<int,int>> origEdges;
    origEdges.reserve(N + 5);
    for (int i = 1; i <= N-1; ++i) {
        int p = inf.readInt(1, i, "p"); // 1 <= p <= i
        origEdges.emplace_back(p, i+1);
    }

    // compute degrees and leaves, then add the outer ring edges between leaves in increasing order
    vector<int> deg(N+1, 0);
    for (auto &e : origEdges) {
        deg[e.first]++; deg[e.second]++;
    }
    vector<int> leaves;
    for (int i = 1; i <= N; ++i) if (deg[i] == 1) leaves.push_back(i);
    sort(leaves.begin(), leaves.end());
    int L = (int)leaves.size();
//    for (auto x: leaves) cerr << x << " "; cerr << endl; 
    if (L >= 2) {
        for (int i = 0; i < L; ++i) {
            int u = leaves[i], v = leaves[(i+1) % L];
            origEdges.emplace_back(u, v);
        }
    }

    // read contestant output
    // NOTE: we do NOT enforce K <= 4N here (user asked to remove that check).
    int K = ouf.readInt(1, 1000000, "K");

    vector<vector<int>> Xi(K+1);
    vector<vector<int>> appears(N+1); // appears[j] = list of indices i such that j in X_i

    for (int i = 1; i <= K; ++i) {
        // allow 0 size
        int printed_sz = ouf.readInt(0, 1000000, "|Xi|");
        unordered_set<int> st;
        vector<int> elems;
        elems.reserve(min(printed_sz, 4));
        for (int t = 0; t < printed_sz; ++t) {
            int x = ouf.readInt(1, N, "elem");
            if (st.insert(x).second) elems.push_back(x);
        }
        if ((int)elems.size() > 4) quitf(_wa, "Xi[%d] has more than 4 distinct elements", i);
        Xi[i] = elems;
        for (int x : Xi[i]) appears[x].push_back(i);
    }

    // read K-1 edges of the new tree
    vector<vector<int>> G(K+1);
    for (int i = 0; i < K-1; ++i) {
        int a = ouf.readInt(1, K, "a");
        int b = ouf.readInt(1, K, "b");
        if (a == b) quitf(_wa, "Self-loop in new tree: %d-%d", a, b);
        G[a].push_back(b);
        G[b].push_back(a);
    }

    // Check new graph is connected (K-1 edges & connected => a tree)
    {
        vector<char> vis(K+1, 0);
        queue<int> q;
        q.push(1);
        vis[1] = 1;
        int cnt = 1;
        while (!q.empty()) {
            int u = q.front(); q.pop();
            for (int v : G[u]) if (!vis[v]) {
                vis[v] = 1; q.push(v); ++cnt;
            }
        }
        if (cnt != K) quitf(_wa, "New graph is not connected (visited %d of %d)", cnt, K);
    }

    // Check each original edge (including outer ring) is covered by some X_i
    for (auto &e : origEdges) {
        int u = e.first, v = e.second;
        bool ok = false;
        // iterate indices of sets that contain u (usually small)
        for (int idx : appears[u]) {
            for (int y : Xi[idx]) if (y == v) { ok = true; break; }
            if (ok) break;
        }
        if (!ok) quitf(_wa, "Original edge (%d,%d) is not covered by any Xi", u, v);
    }

    // For each original vertex j, check S_j = { i | j in X_i } is non-empty and connected in new tree
    vector<int> inSet(K+1, 0), seen(K+1, 0);
    int iter = 1;
    for (int j = 1; j <= N; ++j) {
        auto &nodes = appears[j];
        if (nodes.empty()) quitf(_wa, "Original vertex %d is not present in any Xi", j);

        ++iter;
        for (int v : nodes) inSet[v] = iter;
        queue<int> q;
        q.push(nodes[0]);
        seen[nodes[0]] = iter;
        int cnt = 1;
        while (!q.empty()) {
            int u = q.front(); q.pop();
            for (int v : G[u]) {
                if (inSet[v] == iter && seen[v] != iter) {
                    seen[v] = iter; q.push(v); ++cnt;
                }
            }
        }
        if (cnt != (int)nodes.size()) quitf(_wa, "S_%d is not connected in new tree (%d of %d reachable)", j, cnt, (int)nodes.size());
    }

	double ratio = max(0.0, min(1.0, 1.0 * (5 * N - K) / 2 * N));
    double unbounded_ratio = max(0.0, 1.0 * (5 * N - K) / 2 * N);
	char mes[30];
	sprintf(mes, "Ratio: %lf, RatioUnbounded: %lf", ratio, unbounded_ratio);
	quitp(ratio, "%s", mes);
}

