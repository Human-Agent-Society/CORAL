#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

typedef long long LL;

// Global data for check() convenience
static long long N, M;
static int K;
static vector<pair<int,int>> pts;
static string reason;

bool check() {
    reason.clear();

    // Basic bounds
    if (K < 0 || (long long)K > N * M) {
        reason = "k out of valid range.";
        return false;
    }

    // Range check and duplicates of points
    vector<unsigned long long> enc;
    enc.reserve(K);
    for (int i = 0; i < K; i++) {
        int r = pts[i].first;
        int c = pts[i].second;
        if (r < 1 || r > N || c < 1 || c > M) {
            reason = "Coordinate out of range.";
            return false;
        }
        unsigned long long id = (unsigned long long)(r - 1) * (unsigned long long)M + (unsigned long long)(c - 1);
        enc.push_back(id);
    }
    sort(enc.begin(), enc.end());
    for (int i = 1; i < K; i++) {
        if (enc[i] == enc[i - 1]) {
            reason = "Duplicate coordinates.";
            return false;
        }
    }

    if (K == 0) return true; // empty set is valid

    // If only one row or one column, rectangles are impossible
    if (N == 1 || M == 1) return true;

    // Build adjacency: rows -> columns, cols -> rows
    vector<vector<int>> rows((size_t)N + 1), cols((size_t)M + 1);
    rows.shrink_to_fit();
    cols.shrink_to_fit();
    for (auto &p : pts) {
        rows[p.first].push_back(p.second);
        cols[p.second].push_back(p.first);
    }

    // Sort row column lists for consistent pair keys (light rows)
    for (int r = 1; r <= N; r++) {
        if (!rows[r].empty()) {
            sort(rows[r].begin(), rows[r].end());
        }
    }

    // Heavy-light threshold
    const int B = 300;

    // Heavy rows detection (degree > B)
    vector<int> heavyRows;
    heavyRows.reserve(N);
    for (int r = 1; r <= N; r++) {
        if ((int)rows[r].size() > B) heavyRows.push_back(r);
    }

    // Heavy rows check: for each heavy row, count intersections
    if (!heavyRows.empty()) {
        vector<int> cnt((size_t)N + 1, 0);
        vector<int> touched;
        touched.reserve(N);

        for (int r : heavyRows) {
            // Count how many common columns with each other row
            for (int c : rows[r]) {
                for (int rr : cols[c]) {
                    if (rr == r) continue;
                    if (cnt[rr] == 0) touched.push_back(rr);
                    cnt[rr]++;
                    if (cnt[rr] >= 2) {
                        reason = "Rectangle found (two rows share at least two columns).";
                        return false;
                    }
                }
            }
            // reset
            for (int rr : touched) cnt[rr] = 0;
            touched.clear();
        }
    }

    // Light rows: enumerate column pairs and detect duplicates across rows
    // Only rows with degree >= 2 are relevant
    long long pairEstimate = 0;
    vector<int> lightRows;
    lightRows.reserve(N);
    for (int r = 1; r <= N; r++) {
        int d = (int)rows[r].size();
        if (d >= 2 && d <= B) {
            lightRows.push_back(r);
            pairEstimate += 1LL * d * (d - 1) / 2;
        }
    }
    if (pairEstimate > 0) {
        unordered_map <uint64_t, bool> seen;
        for (int r : lightRows) {
            auto &v = rows[r];
            int d = (int)v.size();
            for (int i = 0; i < d; i++) {
                for (int j = i + 1; j < d; j++) {
                    uint64_t c1 = (uint64_t)v[i];
                    uint64_t c2 = (uint64_t)v[j];
                    uint64_t key = (c1 << 32) | c2; // c1 < c2 due to sorting
                    if (seen.find(key) != seen.end()) {
                        reason = "Rectangle found (a column pair appears in two rows).";
                        return false;
                    } else seen[key] = true;
                }
            }
        }
    }

    return true;
}

int main(int argc, char** argv) {
    registerTestlibCmd(argc, argv);

    // Read input: n, m
    N = inf.readLong(1, (long long)1e9); // bounds here are loose; product constraint is in statement
    M = inf.readLong(1, (long long)1e9);
    // We won't rely on product constraint here; checker tolerates any within memory/time.

    // Read contestant output
    K = ouf.readInt(0, (N > 0 && M > 0 ? (int)min<LL>(N * M, 1000000000LL) : 0));
    pts.resize(K);
    for (int i = 0; i < K; i++) {
        int r = ouf.readInt(1, (int)N);
        int c = ouf.readInt(1, (int)M);
        pts[i] = {r, c};
    }
    // ouf.readEof();

    // Validate
    bool ok = check();
    if (!ok) {
        quitp(0.0, "Invalid output");
    }

    // Compute score ratio = min(k / U(n, m), 1)
    auto computeU = [&](long long n, long long m) -> long long {
        long double sn = sqrt((long double)n);
        long double sm = sqrt((long double)m);
        long double v1 = floor((long double)n * sm + (long double)m);
        long double v2 = floor((long double)m * sn + (long double)n);
        long double v3 = (long double)n * (long double)m;
        long double U = min(v1, min(v2, v3));
        if (U < 0) U = 0;
        long long res = (long long)U;
        return res;
    };

    long long U = computeU(N, M);
    if (U <= 0) {
        // Degenerate, but to be safe
        quitp(K > 0 ? 1.0 : 0.0, "Degenerate U; fallback scoring.");
    }

    long double ratioLD = (long double)K / ((long double) U * 1.5);
    double unbounded_ratio = max(0.0, (double)ratioLD);
    if (ratioLD > 1.0L) ratioLD = 1.0L;
    if (ratioLD < 0.0L) ratioLD = 0.0L;
    double ratio = (double)ratioLD;

    quitp(ratio, "Ratio: %.3f, RatioUnbounded: %.3f", ratio, unbounded_ratio);
    return 0;
}