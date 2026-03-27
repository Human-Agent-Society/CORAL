// Snake interactor (Testlib)
// Build: g++ -std=gnu++17 -O2 -pipe -static -s -o interactor interactor.cc
// Run: ./interactor --inf=instance.txt --ans=best.txt -- ./solution
//
// Hidden instance file (inf):
//   t
//   n1 m1
//   G[1][1] G[1][2] ... G[1][n]
//   ...
//   G[n][1] ... G[n][n]
//   moves_1 (string of 2n-2 chars: 'D' or 'R', for snake of length 1)
//   moves_2 (string of 2n-2 chars: 'D' or 'R', for snake of length 2)
//   ...
//   moves_n (string of 2n-2 chars: 'D' or 'R', for snake of length n)
//   (repeat for each test case)
//
// Answer file (ans):
//   optimal_cost (double, for ratio calculation)
//
// Protocol:
//   - Interactor prints: t
//   - For each test case:
//     - Interactor prints: n m
//     - Interactor prints: n lines of G
//     - Participant makes queries: "? l T" (1 <= l <= n, 1 <= T <= 2n-1)
//       Interactor replies with f(l, T)
//     - Participant answers: "! S1 S2 ... Sm"
//   - After all test cases, scoring is computed
//
// Scoring:
//   single_cost(l, T) = 0.05 + 1/l
//   TOTAL_COST = sum of all query costs
//   if TOTAL_COST <= 500: score = 100
//   if TOTAL_COST >= 2500:  score = 0
//   else: score = 100 * (2500 - TOTAL_COST) / 2000

#include "testlib.h"
#include <iostream>
#include <sstream>
#include <vector>
#include <deque>
#include <algorithm>
#include <string>
#include <climits>
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
    setName("Snake interactor (ratio scoring)");
    registerInteraction(argc, argv);

    // ---- Problem constraints ----
    const int N_MAX = 500;
    const double COST_THRESHOLD_LOW = 500.0;   // Full score threshold
    const double COST_THRESHOLD_HIGH = 2500.0;  // Zero score threshold

    // ---- Read test case count from 'inf' ----
    int t = inf.readInt(1, 100, "t");

    // ---- Read optimal cost from 'ans' ----
    double optimal_cost = ans.readDouble(0.0, 1e9, "optimal_cost");

    // ---- Output t to participant ----
    cout << t << '\n' << flush;

    double total_cost = 0.0;
    int total_queries = 0;

    auto finalize_with_ratio = [&](double ratio, double unbounded_ratio, const string &fmt, auto... args) {
        string base = format(fmt.c_str(), args...);
        quitp(ratio, "%s Ratio: %.6f, RatioUnbounded: %.6f", base.c_str(), ratio, unbounded_ratio);
    };

    auto compute_final_score = [&]() -> pair<double, double> {
        double your_score;
        if (total_cost <= COST_THRESHOLD_LOW) {
            your_score = 100.0;
        } else if (total_cost >= COST_THRESHOLD_HIGH) {
            your_score = 0.0;
        } else {
            your_score = 100.0 * (COST_THRESHOLD_HIGH - total_cost) / (COST_THRESHOLD_HIGH - COST_THRESHOLD_LOW);
        }

        double best_score;
        if (optimal_cost <= COST_THRESHOLD_LOW) {
            best_score = 100.0;
        } else if (optimal_cost >= COST_THRESHOLD_HIGH) {
            best_score = 0.0;
        } else {
            best_score = 100.0 * (COST_THRESHOLD_HIGH - optimal_cost) / (COST_THRESHOLD_HIGH - COST_THRESHOLD_LOW);
        }

        double ratio, unbounded_ratio;
        if (best_score <= 0.0) {
            ratio = (your_score <= 0.0) ? 1.0 : 0.0;
            unbounded_ratio = ratio;
        } else {
            ratio = your_score / best_score;
            if (ratio < 0.0) ratio = 0.0;
            unbounded_ratio = ratio;
            if (ratio > 1.0) ratio = 1.0;
        }
        return {ratio, unbounded_ratio};
    };

    for (int tc = 1; tc <= t; ++tc) {
        // ---- Read test case data ----
        int n = inf.readInt(2, N_MAX, format("n[%d]", tc).c_str());
        int max_m = n * (2 * n - 1);
        int m = inf.readInt(1, max_m, format("m[%d]", tc).c_str());

        // Read grid
        vector<vector<int>> G(n + 1, vector<int>(n + 1));
        for (int i = 1; i <= n; ++i) {
            for (int j = 1; j <= n; ++j) {
                G[i][j] = inf.readInt(1, n * n, format("G[%d][%d][%d]", tc, i, j).c_str());
            }
        }

        // Read n snake move strings (one per snake length l = 1..n)
        // Each string has 2n-2 chars: (n-1) D's and (n-1) R's, first char is D
        vector<string> all_moves(n + 1);
        for (int l = 1; l <= n; ++l) {
            all_moves[l] = inf.readWord();  // readWord() for long strings (no length limit)
            ensuref((int)all_moves[l].size() == 2 * n - 2,
                    "Invalid moves string length for snake %d: expected %d, got %d",
                    l, 2 * n - 2, (int)all_moves[l].size());
            ensuref(all_moves[l][0] == 'D',
                    "First move must be D for snake %d, got '%c'", l, all_moves[l][0]);
            int d_cnt = 0, r_cnt = 0;
            for (char c : all_moves[l]) {
                ensuref(c == 'D' || c == 'R',
                        "Invalid move character '%c' for snake %d", c, l);
                if (c == 'D') d_cnt++; else r_cnt++;
            }
            ensuref(d_cnt == n - 1 && r_cnt == n - 1,
                    "Snake %d: expected %d D's and %d R's, got %d D's and %d R's",
                    l, n - 1, n - 1, d_cnt, r_cnt);
        }

        // ---- Precompute snake head positions for all snakes and times ----
        // head_pos[l][T] = position of snake l's head at time T (1-indexed)
        vector<vector<pair<int, int>>> head_pos(n + 1, vector<pair<int, int>>(2 * n));
        for (int l = 1; l <= n; ++l) {
            head_pos[l][1] = {1, 1};
            int hr = 1, hc = 1;
            for (int mv = 0; mv < 2 * n - 2; ++mv) {
                if (all_moves[l][mv] == 'D') hr++;
                else hc++;
                head_pos[l][mv + 2] = {hr, hc};
            }
        }

        // ---- Precompute f(l, T) for all l and T ----
        // f[l][T] = max value covered by snake l at time T
        // Snake of length l at time T covers:
        //   - head positions at times 1, 2, ..., T (up to l positions)
        //   - if T < l: also initial body positions (1,2), (1,3), ..., (1, l-T+1)
        vector<vector<int>> f(n + 1, vector<int>(2 * n, 0));

        for (int l = 1; l <= n; ++l) {
            for (int T = 1; T <= 2 * n - 1; ++T) {
                int max_val = 0;
                // Head history positions for snake l
                int start_time = (T >= l) ? (T - l + 1) : 1;
                for (int t = start_time; t <= T; ++t) {
                    int r = head_pos[l][t].first;
                    int c = head_pos[l][t].second;
                    max_val = max(max_val, G[r][c]);
                }
                // Initial body positions if T < l
                if (T < l) {
                    // Body positions (1,2), (1,3), ..., (1, l-T+1)
                    for (int j = 2; j <= l - T + 1; ++j) {
                        max_val = max(max_val, G[1][j]);
                    }
                }
                f[l][T] = max_val;
            }
        }

        // ---- Compute the correct answer: m smallest f values ----
        vector<int> all_f_values;
        for (int l = 1; l <= n; ++l) {
            for (int T = 1; T <= 2 * n - 1; ++T) {
                all_f_values.push_back(f[l][T]);
            }
        }
        sort(all_f_values.begin(), all_f_values.end());
        vector<int> correct_answer(all_f_values.begin(), all_f_values.begin() + m);

        // ---- Output n, m, and G to participant ----
        cout << n << ' ' << m << '\n';
        for (int i = 1; i <= n; ++i) {
            for (int j = 1; j <= n; ++j) {
                cout << G[i][j] << " \n"[j == n];
            }
        }
        cout << flush;

        // ---- Handle queries ----
        int query_limit = 120 * n + m;
        int queries_this_case = 0;

        while (true) {
            // Read command token (simple token read without regex pattern)
            string cmd = ouf.readToken();

            if (cmd == "?") {
                // Query: ? l T
                int l = ouf.readInt(1, n, "l");
                int T = ouf.readInt(1, 2 * n - 1, "T");

                ++queries_this_case;
                ++total_queries;

                if (queries_this_case > query_limit) {
                    cout << -1 << '\n' << flush;
                    quitf(_wa, "Query limit exceeded in test case %d: %d > %d. Cost: %.2f",
                          tc, queries_this_case, query_limit, total_cost);
                }

                // Add query cost
                double query_cost = 0.05 + 1.0 / l;
                total_cost += query_cost;

                // Reply with f(l, T)
                cout << f[l][T] << '\n' << flush;
            }
            else if (cmd == "!") {
                // Answer: ! S1 S2 ... Sm
                vector<int> user_answer(m);
                for (int i = 0; i < m; ++i) {
                    user_answer[i] = ouf.readInt(1, n * n, format("answer[%d]", i).c_str());
                }

                // Verify answer
                if (user_answer != correct_answer) {
                    // Find first mismatch
                    for (int i = 0; i < m; ++i) {
                        if (user_answer[i] != correct_answer[i]) {
                            quitf(_wa, "Wrong answer in test case %d at position %d: expected %d, got %d. Cost: %.2f",
                                  tc, i + 1, correct_answer[i], user_answer[i], total_cost);
                        }
                    }
                    quitf(_wa, "Wrong answer in test case %d (length mismatch). Cost: %.2f", tc, total_cost);
                }

                // Answer correct, move to next test case
                break;
            }
            else {
                cout << -1 << '\n' << flush;
                auto [ratio, unbounded_ratio] = compute_final_score();
                quitf(_pe, "Expected '?' or '!' but got '%s'", compress(cmd).c_str());
            }
        }
    }

    // All test cases passed
    auto [ratio, unbounded_ratio] = compute_final_score();

    double your_score;
    if (total_cost <= COST_THRESHOLD_LOW) {
        your_score = 100.0;
    } else if (total_cost >= COST_THRESHOLD_HIGH) {
        your_score = 0.0;
    } else {
        your_score = 100.0 * (COST_THRESHOLD_HIGH - total_cost) / (COST_THRESHOLD_HIGH - COST_THRESHOLD_LOW);
    }

    finalize_with_ratio(ratio, unbounded_ratio,
                        "Accepted. Total queries: %d. Total cost: %.6f. Your score: %.2f",
                        total_queries, total_cost, your_score);

    return 0;
}

