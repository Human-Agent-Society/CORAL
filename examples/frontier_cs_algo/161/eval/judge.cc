#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct DSU {
    int n;
    vector<int> p, sz;
    DSU(int n = 0) { init(n); }
    void init(int n_) {
        n = n_;
        p.resize(n);
        sz.assign(n, 1);
        iota(p.begin(), p.end(), 0);
    }
    int find(int a) {
        if (p[a] == a) return a;
        return p[a] = find(p[a]);
    }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (sz[a] < sz[b]) swap(a, b);
        p[b] = a;
        sz[a] += sz[b];
        return true;
    }
    bool same(int a, int b) { return find(a) == find(b); }
};

struct InputData {
    int n, m, k;
    vector<pair<int,int>> stations;       // (x, y)
    vector<tuple<int,int,long long>> edges; // (u, v, w) 0-based
    vector<pair<int,int>> residents;      // (a, b)
};

struct OutputData {
    vector<int> powers;     // size n, 0..5000
    vector<int> edgeOn;     // size m, 0 or 1
};

static long long computeScore(const InputData& in, const OutputData& out) {
    // Connectivity from node 0 using edges ON
    DSU dsu(in.n);
    for (int j = 0; j < in.m; j++) {
        if (out.edgeOn[j]) {
            int u = std::get<0>(in.edges[j]);
            int v = std::get<1>(in.edges[j]);
            dsu.unite(u, v);
        }
    }
    vector<char> connected(in.n, 0);
    for (int i = 0; i < in.n; i++) connected[i] = dsu.same(0, i);

    // Broadcast coverage
    vector<char> covered(in.k, 0);
    for (int i = 0; i < in.n; i++) {
        if (!connected[i]) continue;
        long long p = out.powers[i];
        long long p2 = p * p;
        long long sx = in.stations[i].first;
        long long sy = in.stations[i].second;
        for (int k = 0; k < in.k; k++) {
            if (covered[k]) continue;
            long long rx = in.residents[k].first;
            long long ry = in.residents[k].second;
            long long dx = sx - rx;
            long long dy = sy - ry;
            long long d2 = dx * dx + dy * dy;
            if (d2 <= p2) covered[k] = 1;
        }
    }
    long long ncovered = 0;
    for (int k = 0; k < in.k; k++) if (covered[k]) ncovered++;

    if (ncovered < in.k) {
        double val = 1e6 * double(ncovered + 1) / double(in.k);
        return llround(val);
    } else {
        long long S = 0;
        for (int i = 0; i < in.n; i++) {
            long long p = out.powers[i];
            S += p * p;
        }
        for (int j = 0; j < in.m; j++) {
            if (out.edgeOn[j]) {
                S += std::get<2>(in.edges[j]);
            }
        }
        double val = 1e6 * (1.0 + 1e8 / (double(S) + 1e7));
        return llround(val);
    }
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    InputData in;
    in.n = inf.readInt();
    in.m = inf.readInt();
    in.k = inf.readInt();
    in.stations.resize(in.n);
    for (int i = 0; i < in.n; i++) {
        int x = inf.readInt();
        int y = inf.readInt();
        in.stations[i] = {x, y};
    }
    in.edges.resize(in.m);
    for (int j = 0; j < in.m; j++) {
        int u = inf.readInt();
        int v = inf.readInt();
        long long w = inf.readLong();
        // Convert to 0-based
        --u; --v;
        in.edges[j] = make_tuple(u, v, w);
    }
    in.residents.resize(in.k);
    for (int i = 0; i < in.k; i++) {
        int a = inf.readInt();
        int b = inf.readInt();
        in.residents[i] = {a, b};
    }

    // Parse output: possibly multiple solutions, only last counts
    vector<OutputData> outs;
    while (!ouf.seekEof()) {
        OutputData out;
        out.powers.resize(in.n);
        for (int i = 0; i < in.n; i++) {
            out.powers[i] = ouf.readInt(0, 5000);
        }
        out.edgeOn.resize(in.m);
        for (int j = 0; j < in.m; j++) {
            out.edgeOn[j] = ouf.readInt(0, 1);
        }
        outs.push_back(std::move(out));
    }

    if (outs.empty()) {
        quitf(_wa, "empty output");
    }

    const OutputData& last = outs.back();
    long long score = computeScore(in, last);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}