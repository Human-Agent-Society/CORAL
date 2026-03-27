#include "testlib.h"
#include <vector>
#include <iostream>
#include <cmath>
#include <algorithm>

using namespace std;

// Maximum number of vertices as per problem constraints (10^6)
const int MAXN = 1000005;
// Logarithm bound for max X. 2^62 > 5 * 10^18.
const int LOGK = 63; 

// Binary lifting table. 
// up[k][u] stores the node reached starting from u after 2^k steps.
// Memory usage: 63 * 10^6 * 4 bytes ≈ 252 MB, well within 1024 MB limit.
int up[LOGK][MAXN];

int main(int argc, char* argv[]) {
    // Initialize testlib environment
    setName("Interactor for Hedgehog Graph with Quadratic Scoring");
    registerInteraction(argc, argv);

    // Read the number of graphs (n) from the test input file
    int n_graphs = inf.readInt(1, 10, "n");
    
    // Send n to the user's standard input
    cout << n_graphs << endl;

    double total_score = 0.0;
    long long tot_moves = 0;
    long long tot_base_move_count = 0;
    double tot_unbounded_score = 0.0;

    for (int g = 0; g < n_graphs; ++g) {
        // --- Read Graph Data ---
        // The user does not see this part directly, they only query it.
        int nodes = inf.readInt(1, 1000000, "num_vertices");
        
        // Read the functional graph structure
        // Format: nodes integers, where the i-th integer is the destination of vertex i
        for (int i = 1; i <= nodes; ++i) {
            up[0][i] = inf.readInt(1, nodes, "next_node");
        }

        // --- Precompute Binary Lifting Table ---
        // This allows us to answer queries in O(log X) time (essentially O(60) ops).
        for (int k = 1; k < LOGK; ++k) {
            for (int i = 1; i <= nodes; ++i) {
                up[k][i] = up[k-1][up[k-1][i]];
            }
        }

        // --- Calculate Ground Truth (Cycle Length) ---
        // Since it's a hedgehog graph, every node eventually reaches the unique cycle.
        // We simulate a jump large enough (> N) to guarantee landing inside the cycle.
        // 2^20 = 1,048,576 > 10^6.
        int curr = 1;
        for (int k = 0; k < 21; ++k) {
            // Check bit (though we just want to jump deep, logical AND is fine if we jump fixed amount)
            // Simpler: Just apply up[20] once if N <= 10^6.
            // But to be generic, let's just use the table to jump 'nodes' steps.
             if ((nodes >> k) & 1) curr = up[k][curr];
        }
        // Just to be absolutely safe against edge cases, jump another large block
        curr = up[20][curr]; 

        // Now 'curr' is guaranteed to be in the cycle. Measure the length.
        int start_node = curr;
        int true_cycle_len = 1;
        int walker = up[0][curr];
        while (walker != start_node) {
            walker = up[0][walker];
            true_cycle_len++;
        }

        // --- Interaction Loop ---
        int queries = 0;
        bool solved = false;
        
        // We set a hard limit slightly above the 0-point threshold to prevent infinite loops.
        // At 2500 queries, score is 0.
        int hard_limit = 2500; 

        while (true) {
            // Read query type from user output
            string type = ouf.readToken("[?!]");
            
            if (type == "?") {
                queries++;
                
                // Read v and x
                int v = ouf.readInt(1, nodes, "v");
                long long x = ouf.readLong(1, 5000000000000000000LL, "x");
                
                // Enforce query limit
                if (queries > hard_limit) {
                    // Tell user they failed (optional protocol, usually implicit by verdict)
                    cout << -1 << endl;
                    quitf(_wa, "Graph %d: Query limit exceeded (>%d)", g + 1, hard_limit);
                }

                // Answer query: Simulate 'x' moves using binary lifting
                int res = v;
                for (int k = 0; k < LOGK; ++k) {
                    if ((x >> k) & 1) {
                        res = up[k][res];
                    }
                }
                cout << res << endl;
            } 
            else if (type == "!") {
                // Read user's answer
                long long user_ans = ouf.readLong(1, (long long)nodes, "answer");
                
                if (user_ans == true_cycle_len) {
                    cout << 1 << endl; // Protocol: 1 means Correct, proceed
                    solved = true;
                } else {
                    cout << -1 << endl; // Protocol: -1 means Incorrect, terminate
                    quitf(_wa, "Graph %d: Wrong cycle length. Expected %d, got %lld", g + 1, true_cycle_len, user_ans);
                }
                break; // Exit loop to process next graph or finish
            }
        }
        tot_moves += queries;
        tot_base_move_count += 900;

        // --- Calculate Score for this Graph ---
        double case_score = 0.0;
        if (solved) {
            if (queries <= 500) {
                case_score = 1.0;
            } else if (queries >= 2500) {
                case_score = 0.0;
            } else {
                // Quadratic Curve: 100% * ( (2500 - Q) / 2000 )^2
                // Closer to 500 => Higher score.
                double q = (double)queries;
                double ratio = (2500.0 - q) / 2000.0;
                case_score = 1.0 * ratio * ratio;
            }
        }
        
        double unbounded_case_score = 1.0 * (2500.0 - queries) / 2000.0;
        unbounded_case_score = unbounded_case_score * unbounded_case_score;
        tot_unbounded_score += unbounded_case_score;
        total_score += case_score;
    }

    // --- Final Verdict ---
    double score_ratio = total_score / (double)n_graphs;
    double unbounded_score_ratio = tot_unbounded_score / (double)n_graphs;
    // Output final score using quitp for partial scoring support
    quitp(score_ratio, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", tot_moves, score_ratio, unbounded_score_ratio);

    return 0;
}