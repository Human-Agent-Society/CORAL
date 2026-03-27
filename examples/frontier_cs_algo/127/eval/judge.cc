// The Big Prize interactor (stdout version; 0-based indices; Testlib)
// Time limit and memory limit are enforced by the judge runner, not here.
//
// Build example (Linux):
//   g++ -std=gnu++17 -O2 -pipe -static -s -o interactor interactor.cpp
//
// Run example (with testlib):
//   ./interactor --inf=instance.txt --ans=best.txt -- -team-command-
//
// Hidden instance file (inf):
//   n
//   t0 t1 ... t{n-1}
//
// Answer file (.ans):
//   optimal_queries
//
// Protocol to participant (stdout/stdin):
//   - Interactor prints: n
//   - For each query, participant prints: "? i"   (0 <= i < n), then flushes
//     Interactor replies: "a0 a1"
//   - When done, participant prints: "! i"   (diamond index), then exits.
//
// Scoring: your_score = max(0, 5000 - q)
//          best_score = max(0, 5000 - optimal_queries)
//          ratio = your_score / best_score  (with special-casing best_score == 0)

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

// ---------- helpers ----------
static inline bool parse_ll(const string& s, long long& x) {
    if (s.empty()) return false;
    size_t i = 0;
    if (s[0] == '+' || s[0] == '-') i = 1;
    if (i == s.size()) return false;
    for (; i < s.size(); ++i) if (s[i] < '0' || s[i] > '9') return false;
    try {
        size_t pos = 0; long long v = stoll(s, &pos, 10);
        if (pos != s.size()) return false; x = v; return true;
    } catch (...) { return false; }
}
static inline bool parse_int32(const string& s, int& x) {
    long long t; if (!parse_ll(s, t)) return false;
    if (t < INT_MIN || t > INT_MAX) return false; x = (int)t; return true;
}

// Simple Fenwick (1-indexed)
struct Fenwick {
    int n; vector<int> f;
    Fenwick(int n = 0): n(n), f(n + 1, 0) {}
    void add(int i, int v) { for (; i <= n; i += i & -i) f[i] += v; }
    int sum(int i) const { int s = 0; for (; i > 0; i -= i & -i) s += f[i]; return s; }
};

int main(int argc, char* argv[]) {
    setName("The Big Prize interactor (stdout version; 0-based; ratio scoring)");
    registerInteraction(argc, argv);

    // ---- Problem constraints ----
    const int N_MIN = 3;
    const int N_MAX = 200000;
    const int SCORE_BASE  = 5000;                 // scoring: 5000 - queries
    const int QUERY_LIMIT = 1000000;              // generous hard cap to prevent infinite loops

    // ---- Read hidden instance from 'inf': n and types t[0..n-1] ----
    int n = inf.readInt(N_MIN, N_MAX, "n");
    vector<int> t(n);
    for (int i = 0; i < n; ++i) {
        t[i] = inf.readInt(1, 1000000000, format("t[%d]", i).c_str());
    }

    // ---- Validate instance constraints ----
    int v = 0;
    for (int x : t) v = max(v, x);

    // there is exactly one diamond (type 1)
    int cnt_type1 = 0;
    for (int x : t) if (x == 1) ++cnt_type1;
    ensuref(cnt_type1 == 1, "Invalid instance: expected exactly one type-1 (diamond), got %d.", cnt_type1);

    // count per type
    vector<long long> cnt(v + 1, 0);
    for (int x : t) cnt[x]++;

    // growth rule: for all 2..v, cnt[t] > (cnt[t-1])^2
    for (int typ = 2; typ <= v; ++typ) {
        long long prev = cnt[typ - 1];
        long long need = prev * prev; // may be large; compare with long long
        ensuref(cnt[typ] > need,
                "Invalid instance: count[type=%d]=%lld is not strictly greater than (count[type=%d])^2=%lld.",
                typ, cnt[typ], typ - 1, need);
    }

    // ---- Precompute answers (a0, a1) for all positions using Fenwick ----
    // Compress types to ranks 1..V in increasing order of "type number" (1 is smallest)
    vector<int> comp = t;
    sort(comp.begin(), comp.end());
    comp.erase(unique(comp.begin(), comp.end()), comp.end()); // size == v
    // Map type -> rank (1..v) preserving order
    auto getRank = [&](int x) {
        // lower_bound finds index where comp[idx] == x
        int idx = int(lower_bound(comp.begin(), comp.end(), x) - comp.begin()) + 1; // 1-based
        return idx;
    };
    const int V = (int)comp.size();
    vector<int> rankv(n);
    for (int i = 0; i < n; ++i) rankv[i] = getRank(t[i]);

    vector<int> a0(n, 0), a1(n, 0);

    // a0[i] = number of more-expensive prizes to the LEFT of i
    // "More expensive" => smaller type number => smaller rank
    {
        Fenwick fw(V);
        for (int i = 0; i < n; ++i) {
            int r = rankv[i];
            a0[i] = fw.sum(r - 1);
            fw.add(r, 1);
        }
    }
    // a1[i] = number of more-expensive prizes to the RIGHT of i
    {
        Fenwick fw(V);
        for (int i = n - 1; i >= 0; --i) {
            int r = rankv[i];
            a1[i] = fw.sum(r - 1);
            fw.add(r, 1);
        }
    }

    // ---- Diamond index (type 1) ----
    int diamondIndex = -1;
    for (int i = 0; i < n; ++i) if (t[i] == 1) { diamondIndex = i; break; }
    ensuref(diamondIndex != -1, "Internal error: diamond index not found.");

    // ---- Read optimal #queries from '.ans' ----
    int optimal_queries = ans.readInt(0, QUERY_LIMIT, "optimal_queries");

    // ---- Public output: announce n and FLUSH ----
    cout << n << '\n' << flush;

    int queries = 0; // number of answered '?' queries

    auto finalize_with_ratio = [&](double ratio, double unbounded_ratio, const string &fmt, auto... args) {
        string base = format(fmt.c_str(), args...);
        quitp(ratio, "%s Ratio: %.6f, RatioUnbounded: %.6f", base.c_str(), ratio, unbounded_ratio);
    };

    while (true) {
        // Expect either "?" or "!" from the participant
        string cmd = ouf.readToken();

        if (cmd == "?") {
            // Read token for i and validate manually (in-bounds check)
            string si = ouf.readToken();

            int i = 0;
            bool okI = parse_int32(si, i);

            if (!okI) {
                // Return an explicit invalid response to avoid hanging the participant
                cout << -1 << ' ' << -1 << '\n' << flush;
                quitf(_pe, "Invalid query: expected integer index for i, got '%s'.",
                      compress(si).c_str());
            }

            if (i < 0 || i >= n) {
                cout << -1 << ' ' << -1 << '\n' << flush;
                quitf(_wa, "Query out of bounds: i=%d (valid range is [0,%d]).", i, n - 1);
            }

            if (queries > QUERY_LIMIT) {
                cout << -1 << ' ' << -1 << '\n' << flush;
                finalize_with_ratio(0.0, 0.0, "Query limit exceeded: %d > %d.", queries, QUERY_LIMIT);
            }

            // Answer: a0[i] a1[i]
            cout << a0[i] << ' ' << a1[i] << '\n' << flush;
            ++queries;
        }
        else if (cmd == "!") {
            // Read final answer: exactly one integer index in [0..n-1]
            int gi = ouf.readInt(0, n - 1, "answer_index");

            if (gi != diamondIndex) {
                // Wrong answer -> ratio 0.0
                finalize_with_ratio(0.0, 0.0,
                                    "Wrong answer: reported index %d, diamond is at %d. Queries used: %d.",
                                    gi, diamondIndex, queries);
            }

            // ---- Compute scores and ratio ----
            int your_raw_nonneg = max(0, SCORE_BASE - queries);
            int best_raw_nonneg = max(0, SCORE_BASE - optimal_queries);

            double your_score = (double)your_raw_nonneg;
            double best_score = (double)best_raw_nonneg;

            double ratio;
            double unbounded_ratio;
            if (best_score <= 0.0) {
                ratio = (your_score <= 0.0) ? 1.0 : 0.0;
                unbounded_ratio = ratio;
            } else {
                ratio = your_score / best_score;
                if (ratio < 0.0) ratio = 0.0;
                unbounded_ratio = ratio;
                if (ratio > 1.0) ratio = 1.0;
            }

            finalize_with_ratio(ratio, unbounded_ratio,
                                "Accepted. Queries used: %d. Your score = 5000 - %d = %d. "
                                "Optimal queries: %d. Best score = 5000 - %d = %d.",
                                queries, queries, your_raw_nonneg,
                                optimal_queries, optimal_queries, best_raw_nonneg);
        }
        else {
            // Unexpected token
            cout << -1 << ' ' << -1 << '\n' << flush;
            quitf(_pe, "Expected '?' or '!' but got '%s'.", compress(cmd).c_str());
        }
    }
}
