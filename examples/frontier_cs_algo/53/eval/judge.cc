#include "testlib.h"
#include <vector>
#include <algorithm>
#include <iostream>
#include <cmath>
#include <iomanip>

using namespace std;

// Helper to calculate log2 ceiling for optimal query count
int get_log_bound(int n) {
    // Equivalent to ceil(log2(n))
    if (n <= 1) return 0;
    return 32 - __builtin_clz(n - 1);
}

int main(int argc, char* argv[]) {
    // Initialize the testlib environment
    setName("Grader for G2 (Hard Version) with Efficiency Scoring");
    registerInteraction(argc, argv);

    // Read the total number of test cases
    int t = inf.readInt(1, 500, "t");
    cout << t << endl;

    double total_score = 0.0;
    double tot_unbounded_score = 0.0;

    int num_queries = 0;
    int num_base_queries = 0;

    for (int test_case = 1; test_case <= t; ++test_case) {
        // --- Read Test Case Data ---
        int n = inf.readInt(4, 100, "n");
        
        vector<int> p(n);
        vector<bool> seen(n + 1, false);
        for (int i = 0; i < n; ++i) {
            p[i] = inf.readInt(1, n, "p_i");
            if (p[i] == i + 1) quitf(_fail, "Invalid input: Fixed point found");
            if (seen[p[i]]) quitf(_fail, "Invalid input: Duplicate found");
            seen[p[i]] = true;
        }

        // --- Interaction ---
        cout << n << endl; // Send n
        int k = ouf.readInt(1, n, "k"); // Read k

        // Hard limit to prevent infinite loops, but scoring ignores it if it's very high
        // We set a safety break at 10n just to keep the judge sane, 
        // but the score will likely be 0 long before that.
        int safety_limit = 16.0 * n; 
        int queries = 0;
        bool case_solved = false;

        while (!case_solved) {
            string mode = ouf.readToken("[?!]");

            if (mode == "!") {
                // Check answer
                vector<int> guess(n);
                for (int i = 0; i < n; ++i) guess[i] = ouf.readInt(1, n, "guess_i");

                if (guess == p) {
                    case_solved = true;
                } else {
                    quitf(_wa, "Test Case %d: Wrong guess.", test_case);
                }
            } else {
                // Process Query
                queries++;
                if (queries > safety_limit) {
                    quitf(_wa, "Test Case %d: Safety query limit exceeded (> %d)", test_case, safety_limit);
                }

                vector<int> q(n);
                vector<bool> q_seen(n + 1, false);
                for (int i = 0; i < n; ++i) {
                    q[i] = ouf.readInt(1, n, "q_i");
                    if (q[i] < 1 || q[i] > n || q_seen[q[i]]) {
                        quitf(_wa, "Test Case %d: Invalid query permutation", test_case);
                    }
                    q_seen[q[i]] = true;
                }

                int count = 0;
                for (int i = 1; i <= n; ++i) {
                    for (int j = 1; j <= n; ++j) {
                        if (i >= j || i == k) continue;
                        if (p[q[i - 1] - 1] == q[j - 1]) count++;
                    }
                }
                cout << count << endl;
            }
        }

        // --- Calculate Score for this Case ---
        // Scoring Parameters
        double L = 20.0 * n;                           // Lower Bound (0 points)
        double O = 1.0 * n;            // Upper Bound (100 points)
        double score = 0.0;

        num_queries += queries;
        num_base_queries += L;

        if (queries <= O) {
            score = 1.0;
        } else if (queries >= L) {
            score = 0.0;
        } else {
            // Quadratic Curve: ( (L - Q) / (L - O) )^2
            // As Q approaches L, the numerator approaches 0.
            // As Q approaches O, the fraction approaches 1.
            double ratio = (L - queries) / (L - O);
            score = ratio * ratio;
        }

        double unbounded_score = max(0.0, (L - queries) / (L - O));
        unbounded_score = unbounded_score * unbounded_score;
        tot_unbounded_score += unbounded_score;
        
        total_score += score;
    }

    // --- Final Verdict ---
    double score_ratio = total_score / t;

    double unbounded_score_ratio = tot_unbounded_score / t;
    // Output partial score. "quitp" is testlib's function for partial credit.

    quitp(score_ratio, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", num_queries, score_ratio, unbounded_score_ratio);
    
    return 0;
}