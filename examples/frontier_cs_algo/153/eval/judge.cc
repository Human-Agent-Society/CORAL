#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int N = 400;
static const int K = 5;
static const int M = (N - 1) * K;

struct DSU {
    vector<int> p, sz;
    DSU(int n = 0) { init(n); }
    void init(int n) {
        p.resize(n);
        sz.assign(n, 1);
        iota(p.begin(), p.end(), 0);
    }
    int find(int x) {
        if (p[x] == x) return x;
        return p[x] = find(p[x]);
    }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (sz[a] < sz[b]) swap(a, b);
        p[b] = a;
        sz[a] += sz[b];
        return true;
    }
    int size(int x) {
        x = find(x);
        return sz[x];
    }
    bool same(int a, int b) { return find(a) == find(b); }
};

static inline string trim_str(const string &s) {
    size_t l = 0, r = s.size();
    while (l < r && isspace((unsigned char)s[l])) l++;
    while (r > l && isspace((unsigned char)s[r - 1])) r--;
    return s.substr(l, r - l);
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    vector<pair<int,int>> ps(N);
    vector<pair<int,int>> es(M);
    vector<long long> cs(M);

    // Read points
    for (int i = 0; i < N; i++) {
        int x = inf.readInt();
        int y = inf.readInt();
        ps[i] = {x, y};
    }
    // Read edges
    for (int i = 0; i < M; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        es[i] = {u, v};
    }
    // Read costs
    for (int i = 0; i < M; i++) {
        long long c = inf.readLong();
        cs[i] = c;
    }

    // Send initial data to contestant
    for (int i = 0; i < N; i++) {
        cout << ps[i].first << " " << ps[i].second << endl;
    }
    for (int i = 0; i < M; i++) {
        cout << es[i].first << " " << es[i].second << endl;
    }
    cout.flush();

    DSU uf(N);
    long long chosen_cost = 0;

    // Interactive loop
    for (int i = 0; i < M; i++) {
        // Send current edge cost
        cout << cs[i] << endl;
        cout.flush();

        // Read non-empty line, skip blanks and lines starting with '#'
        string line;
        do {
            line = ouf.readLine();
            line = trim_str(line);
        } while (line.empty() || line[0] == '#');

        if (!(line == "0" || line == "1")) {
            quitf(_wa, "illegal output (%s)", line.c_str());
        }
        int take = (line[0] == '1') ? 1 : 0;
        if (take == 1) {
            uf.unite(es[i].first, es[i].second);
            chosen_cost += cs[i];
        }
    }

    // Check connectivity
    if (uf.size(0) != N) {
        quitf(_wa, "not connected");
    }

    // Compute MST on all edges with given costs
    vector<int> idx(M);
    iota(idx.begin(), idx.end(), 0);
    sort(idx.begin(), idx.end(), [&](int a, int b) {
        if (cs[a] != cs[b]) return cs[a] < cs[b];
        if (es[a].first != es[b].first) return es[a].first < es[b].first;
        return es[a].second < es[b].second;
    });
    DSU mst_dsu(N);
    long long mst_cost = 0;
    for (int id : idx) {
        if (mst_dsu.unite(es[id].first, es[id].second)) {
            mst_cost += cs[id];
        }
    }

    if (chosen_cost <= 0) {
        quitf(_wa, "total chosen cost is non-positive");
    }

    long long score = llround(1e8L * (long double) mst_cost / (long double) chosen_cost);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
    // quitf(_wa, "score (%lld)", score);
    return 0;
}