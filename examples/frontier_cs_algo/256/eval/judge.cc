#include "testlib.h"
#include <vector>
#include <iostream>
#include <string>
#include <algorithm>
#include <cstring>

using namespace std;

// Maximum grid size as per constraints (N < 50)
const int MAXN = 55;

// DP/Memoization table for palindrome path checking
// memo[r1][c1][r2][c2]:
// -1: Unknown/Uncomputed
//  0: False (No palindromic path)
//  1: True (Exists palindromic path)
short memo[MAXN][MAXN][MAXN][MAXN];
vector<string> grid;
int n;

// Helper to check if coordinates are within bounds
bool valid(int r, int c) {
    return r >= 0 && r < n && c >= 0 && c < n;
}

// Recursive function with memoization to check for palindromic path
// Moves: Start goes Right(0,1) or Down(1,0)
//        End goes Left(0,-1) or Up(-1,0) [Reversed Right/Down]
bool solve(int r1, int c1, int r2, int c2) {
    // If characters don't match, this path isn't a palindrome
    if (grid[r1][c1] != grid[r2][c2]) return false;
    
    // If paths have crossed or met
    // Exact meeting
    if (r1 == r2 && c1 == c2) return true;
    // Adjacent meeting (r1, c1) is neighbor of (r2, c2)
    // Since start moves R/D and end moves L/U, they meet if dist is 1.
    if (r1 + c1 + 1 == r2 + c2) return true;

    // Check memoization
    if (memo[r1][c1][r2][c2] != -1) {
        return memo[r1][c1][r2][c2];
    }

    bool res = false;
    // Try all valid next steps
    // Start moves: (r1+1, c1) OR (r1, c1+1)
    // End moves:   (r2-1, c2) OR (r2, c2-1)
    
    // Option 1: Start Down, End Up
    if (valid(r1 + 1, c1) && valid(r2 - 1, c2)) 
        if (solve(r1 + 1, c1, r2 - 1, c2)) res = true;
    
    // Option 2: Start Down, End Left
    if (!res && valid(r1 + 1, c1) && valid(r2, c2 - 1))
        if (solve(r1 + 1, c1, r2, c2 - 1)) res = true;

    // Option 3: Start Right, End Up
    if (!res && valid(r1, c1 + 1) && valid(r2 - 1, c2))
        if (solve(r1, c1 + 1, r2 - 1, c2)) res = true;

    // Option 4: Start Right, End Left
    if (!res && valid(r1, c1 + 1) && valid(r2, c2 - 1))
        if (solve(r1, c1 + 1, r2, c2 - 1)) res = true;

    return memo[r1][c1][r2][c2] = res;
}

int main(int argc, char* argv[]) {
    // Initialize testlib environment
    setName("Interactor for Palindromic Paths (Codeforces 1205C) with Quadratic Scoring");
    registerInteraction(argc, argv);

    // The provided gen_data.py generates files with N then Grid.
    // It creates exactly ONE test case per file.
    int n_graphs = 1; 

    double total_score = 0.0;
    long long tot_moves = 0;
    double tot_unbounded_score = 0.0;

    for (int g = 0; g < n_graphs; ++g) {
        // --- Read Grid Data ---
        n = inf.readInt(3, 49, "n"); // 3 <= n < 50, odd
        grid.clear();
        for (int i = 0; i < n; ++i) {
            grid.push_back(inf.readToken("[01]+", "row"));
        }

        // --- Reset Memoization for this test case ---
        // Since MAXN is small (50), sizeof(memo) is approx 50^4 * 2 bytes = 12.5MB.
        // memset is fast enough.
        memset(memo, -1, sizeof(memo));

        // --- Interaction ---
        cout << n << endl; // Send n to user

        double K_BASE = n * n / 2;
        double K_ZERO = n * n * 2;

        int queries = 0;
        bool solved = false;
        int hard_limit = (int)K_ZERO + 100; // Allow slightly more to gracefully fail

        while (true) {
            string type = ouf.readToken("[?!]");

            if (type == "?") {
                queries++;
                
                if (queries > hard_limit) {
                    cout << -1 << endl;
                    quitf(_wa, "Test case %d: Query limit exceeded (>%d)", g + 1, hard_limit);
                }

                // Format: ? x1 y1 x2 y2
                // 1-based indexing in input, convert to 0-based for logic
                int x1 = ouf.readInt(1, n, "x1") - 1;
                int y1 = ouf.readInt(1, n, "y1") - 1;
                int x2 = ouf.readInt(1, n, "x2") - 1;
                int y2 = ouf.readInt(1, n, "y2") - 1;

                // Validate constraints: x1 <= x2, y1 <= y2, x1+y1+2 <= x2+y2
                if (x1 > x2 || y1 > y2) {
                    quitf(_wa, "Invalid query range: (%d,%d) to (%d,%d)", x1+1, y1+1, x2+1, y2+1);
                }
                if ((x1 + y1) + 2 > (x2 + y2)) {
                    quitf(_wa, "Query cells are too close or adjacent: (%d,%d) to (%d,%d)", x1+1, y1+1, x2+1, y2+1);
                }

                // Perform check
                // We check if a palindromic path exists from (x1,y1) to (x2,y2)
                bool exists = solve(x1, y1, x2, y2);
                cout << (exists ? 1 : 0) << endl;
            } 
            else if (type == "!") {
                // Read user's answer grid
                bool correct = true;
                for (int i = 0; i < n; ++i) {
                    string row = ouf.readToken("[01]+", "user_row");
                    if (row != grid[i]) {
                        correct = false;
                    }
                }

                if (correct) {
                    // Protocol: no specific response needed after !, just terminate logic
                    solved = true;
                } else {
                    // For this problem, if the answer is wrong, we should WA.
                    quitf(_wa, "Test case %d: output grid does not match expected grid.", g + 1);
                }
                break; 
            }
        }

        tot_moves += queries;

        // --- Calculate Score ---
        // Formula: Score = max(0, 100 * ((K_zero - Q) / (K_zero - K_base))^2)
        
        double raw_ratio = 0.0;
        if (solved) {
            // raw_ratio represents the term inside the square: (5000 - Q) / 2500
            double q = (double)queries;
            double term = (K_ZERO - q) / (K_ZERO - K_BASE);
            
            // Calculate squared score ratio
            raw_ratio = term * term;
        }

        // Capped Score (0 to 1.0) for standard system compatibility
        // If queries < 2500, score is still capped at 1.0 for "total_score"
        // If queries > 5000, score is 0.
        double capped_ratio = raw_ratio;
        if (queries < K_BASE) capped_ratio = 1.0; 
        if (queries >= K_ZERO) capped_ratio = 0.0;
        if (!solved) capped_ratio = 0.0;

        total_score += capped_ratio;

        // Unbounded Score (allows > 1.0)
        // Statement: "If your solution uses fewer than n * n queries... score will exceed 100 points"
        double unbounded_ratio = raw_ratio;
        if (queries >= K_ZERO) unbounded_ratio = 0.0;
        if (!solved) unbounded_ratio = 0.0;

        tot_unbounded_score += unbounded_ratio;
    }

    // --- Final Verdict ---
    double score_ratio = total_score / (double)n_graphs;
    double unbounded_score_ratio = tot_unbounded_score / (double)n_graphs;

    // Use quitp exactly as requested in the example
    quitp(score_ratio, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", tot_moves, score_ratio, unbounded_score_ratio);

    return 0;
}