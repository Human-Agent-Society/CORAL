#include "testlib.h"
#include <vector>
#include <iostream>
#include <algorithm>
#include <cmath>
#include <string>

using namespace std;

// Calculate the base limit for full score (100 pts / 1.0 ratio)
// Based on the problem statement: 2n^2 - 2n + 1 races are sufficient.
long long get_base_limit(int n) {
    return n * n;
}

// Calculate the zero score limit.
// In statement.txt, Base=200000 and Zero=400000, so Zero is 2x Base.
// We apply this ratio to the per-test-case logic.
long long get_zero_limit(int n) {
    return 4LL * get_base_limit(n);
}

int main(int argc, char* argv[]) {
    // Initialize testlib
    setName("Interactor for Pepe Racing with Quadratic Scoring");
    registerInteraction(argc, argv);

    // Read number of test cases
    int t = inf.readInt(1, 10000, "t");
    cout << t << endl; // Send t to user

    double total_score = 0.0;
    double total_unbounded_score = 0.0;
    long long total_queries = 0;

    for (int tc = 0; tc < t; ++tc) {
        // --- Read Test Case Data ---
        // Format: "n manual"
        int n = inf.readInt(2, 20, "n");
        inf.readToken("manual"); 
        
        // Read hidden speeds permutation
        int num_pepes = n * n;
        vector<int> speeds(num_pepes + 1);
        vector<pair<int, int>> sorted_pepes; // Stores {speed, label}
        
        for (int i = 1; i <= num_pepes; ++i) {
            speeds[i] = inf.readInt(1, num_pepes, "speed");
            sorted_pepes.push_back({speeds[i], i});
        }
        // Sort to determine the correct answer (descending speed)
        sort(sorted_pepes.rbegin(), sorted_pepes.rend());

        // --- Start Interaction for this case ---
        cout << n << endl; // Send n to user

        long long queries_count = 0;
        long long K_base = get_base_limit(n);
        long long K_zero = get_zero_limit(n);
        
        // Hard limit to prevent infinite loops (well above zero score threshold)
        long long hard_limit = K_zero + 2000; 

        while (true) {
            string type = ouf.readToken("[?!]");
            
            if (type == "?") {
                queries_count++;
                
                // Safety check for excessive queries
                if (queries_count > hard_limit) {
                    quitf(_wa, "Test case %d: Query limit exceeded reasonable bound (>%lld)", tc + 1, hard_limit);
                }

                vector<int> race(n);
                vector<bool> used(num_pepes + 1, false);
                int max_speed = -1;
                int winner = -1;

                for (int i = 0; i < n; ++i) {
                    race[i] = ouf.readInt(1, num_pepes, "pepe_index");
                    
                    // Validate index range
                    if (race[i] < 1 || race[i] > num_pepes) {
                        quitf(_wa, "Test case %d: Invalid pepe label %d", tc + 1, race[i]);
                    }
                    // Validate distinctness
                    if (used[race[i]]) {
                        quitf(_wa, "Test case %d: Duplicate pepe %d in race", tc + 1, race[i]);
                    }
                    used[race[i]] = true;
                    
                    // Find the fastest in this race
                    if (speeds[race[i]] > max_speed) {
                        max_speed = speeds[race[i]];
                        winner = race[i];
                    }
                }
                
                // Return winner
                cout << winner << endl;

            } else { // type == "!"
                // Verify Answer
                // User must provide n^2 - n + 1 labels
                int count_needed = num_pepes - n + 1;
                for (int i = 0; i < count_needed; ++i) {
                    int p = ouf.readInt(1, num_pepes, "ans_index");
                    
                    // Check if the i-th printed pepe is indeed the i-th fastest
                    if (p != sorted_pepes[i].second) {
                        quitf(_wa, "Test case %d: Wrong answer at position %d. Expected label %d (speed %d), got label %d (speed %d)", 
                              tc + 1, i + 1, sorted_pepes[i].second, sorted_pepes[i].first, p, speeds[p]);
                    }
                }
                // If we pass the loop, the answer is correct.
                // Move to next test case.
                break; 
            }
        }
        
        total_queries += queries_count;

        // --- Calculate Score for this Test Case ---
        // Formula: Score = ((K_zero - Q) / (K_zero - K_base))^2
        // If Q >= K_zero, Score = 0.
        
        double raw_score = 0.0;
        
        if (queries_count < K_zero) {
            double term = (double)(K_zero - queries_count) / (double)(K_zero - K_base);
            raw_score = term * term;
        } else {
            raw_score = 0.0;
        }

        // Unbounded score accumulates the raw result (can be > 1.0 if Q < K_base)
        total_unbounded_score += raw_score;

        // Capped score for standard grading (max 1.0)
        double capped_score = raw_score;
        if (queries_count <= K_base) {
            capped_score = 1.0;
        } else if (queries_count >= K_zero) {
            capped_score = 0.0;
        }
        // If between base and zero, capped_score equals raw_score (which is < 1.0)
        
        total_score += capped_score;
    }

    // --- Final Verdict ---
    double avg_score = total_score / (double)t;
    double avg_unbounded = total_unbounded_score / (double)t;

    // Output formatted exactly as requested
    quitp(avg_score, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", total_queries, avg_score, avg_unbounded);

    return 0;
}