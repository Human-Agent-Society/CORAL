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

int main(int argc, char* argv[]) {
    setName("Permutation OR interactor (stdout version; optimal-queries + ratio + in-bounds checks)");
    registerInteraction(argc, argv);

    // ---- Problem constraints ----
    const int N_MIN = 3;
    const int N_MAX = 2048;
    const int QUERY_LIMIT = 4269;            // hard limit for answered queries
    const int SCORE_BASE  = 4269;            // scoring: (5000 - queries) / 10
    const double MAX_SCORE = SCORE_BASE / 10.0; // 500.0

    // ---- Read hidden instance from 'inf': n and permutation p[1..n] ----
    int n = inf.readInt(N_MIN, N_MAX, "n");
    vector<int> p(n + 1);
    for (int i = 1; i <= n; ++i) {
        p[i] = inf.readInt(0, n - 1, format("p[%d]", i).c_str());
    }

    // Validate 'p' is a permutation of [0..n-1]
    vector<int> cnt(n, 0);
    for (int i = 1; i <= n; ++i) ++cnt[p[i]];
    for (int v = 0; v < n; ++v) {
        ensuref(cnt[v] == 1, "Provided p is not a permutation: value %d occurs %d times.", v, cnt[v]);
    }

    // ---- Read optimal #queries from '.ans' ----
    // (This is the number of queries an optimal solution needs.)
    int optimal_queries = ans.readInt(0, QUERY_LIMIT, "optimal_queries");

    // ---- Public output: announce n and FLUSH ----
    cout << n << '\n' << flush;

    int queries = 0; // number of answered '?' queries

    auto finalize_with_ratio = [&](double ratio, double unbounded_ratio, const string &fmt, auto... args) {
        string base = format(fmt.c_str(), args...);
        quitp(ratio, "%s Ratio: %.4f, RatioUnbounded: %.4f", base.c_str(), ratio, unbounded_ratio);
    };

    while (true) {
        // Expect either "?" or "!" from the participant
        string cmd = ouf.readToken();

        if (cmd == "?") {
            // Read tokens for i, j and validate manually (in-bounds check)
            string si = ouf.readToken();
            string sj = ouf.readToken();

            int i = 0, j = 0;
            bool okI = parse_int32(si, i);
            bool okJ = parse_int32(sj, j);

            if (!okI || !okJ) {
                cout << -1 << '\n' << flush;
                quitf(_pe, "Invalid query: expected integers for i and j, got '%s' and '%s'.",
                      compress(si).c_str(), compress(sj).c_str());
            }

            if (i < 1 || i > n || j < 1 || j > n) {
                cout << -1 << '\n' << flush;
                quitf(_wa, "Query out of bounds: i=%d, j=%d (valid range is [1,%d]).", i, j, n);
            }

            if (i == j) {
                cout << -1 << '\n' << flush;
                quitf(_wa, "Invalid query: i == j (%d).", i);
            }

            if (queries > QUERY_LIMIT) {
                cout << -1 << '\n' << flush;
                finalize_with_ratio(0.0, 0.0, "Query limit exceeded: %d > %d.", queries, QUERY_LIMIT);
            }

            int answ = p[i] | p[j];
            cout << answ << '\n' << flush;
            ++queries;
        }
        else if (cmd == "!") {
            // Read final answer: exactly n integers in [0..n-1]
            vector<int> guess(n + 1);
            for (int i = 1; i <= n; ++i) {
                guess[i] = ouf.readInt(0, n - 1, format("ans[%d]", i).c_str());
            }

            // Check that guess is a permutation
            vector<int> cg(n, 0);
            for (int i = 1; i <= n; ++i) ++cg[guess[i]];
            for (int v = 0; v < n; ++v) {
                if (cg[v] != 1) {
                    finalize_with_ratio(0.0, 0.0,
                                        "Final sequence is not a permutation of [0..%d]: value %d occurs %d times. Queries used: %d.",
                                        n - 1, v, cg[v], queries);
                }
            }

            // Check exact equality with hidden permutation
            int first_bad = -1;
            for (int i = 1; i <= n; ++i) {
                if (guess[i] != p[i]) { first_bad = i; break; }
            }
            if (first_bad != -1) {
                finalize_with_ratio(0.0, 0.0,
                                    "Wrong permutation at position %d: got %d, expected %d. Queries used: %d.",
                                    first_bad, guess[first_bad], p[first_bad], queries);
            }

            // ---- Compute scores and ratio ----
            int ai_raw_nonneg  = max(0, SCORE_BASE - queries);
            int opt_raw_nonneg = max(0, SCORE_BASE - optimal_queries);

            double ai_score  = ai_raw_nonneg  / 10.0;
            double opt_score = opt_raw_nonneg / 10.0;

            double ratio, unbounded_ratio = 1.0;
            if (opt_score <= 0.0) {
                ratio = (ai_score <= 0.0) ? 1.0 : 0.0;
            } else {
                ratio = ai_score / opt_score;
                if (ratio < 0.0) ratio = 0.0;
                unbounded_ratio = max(0.0, ratio);
                if (ratio > 1.0) ratio = 1.0;
            }

            finalize_with_ratio(ratio, unbounded_ratio,
                                "Accepted. Queries used: %d. Your score = (4269 - %d) / 10 = %.1f. "
                                "Optimal queries: %d. Optimal score = (4269 - %d) / 10 = %.1f.",
                                queries, queries, ai_score,
                                optimal_queries, optimal_queries, opt_score);
        }
        else {
            // Unexpected token
            cout << -1 << '\n' << flush;
            quitf(_pe, "Expected '?' or '!' but got '%s'.", compress(cmd).c_str());
        }
    }
}
