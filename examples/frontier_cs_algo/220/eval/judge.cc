#include "testlib.h"
#include <iostream>
#include <algorithm>
#include <cstdio>

using namespace std;

const int N = 521;
int n, c[N][N], a[N];

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input: n players, each has n cards
    n = inf.readInt();
    for (int i = 1; i <= n; i++) {
        for (int j = 1; j <= n; j++) {
            int x = inf.readInt();
            if (x < 1 || x > n) {
                quitf(_fail, "Invalid input: card number %d out of range [1, %d]", x, n);
            }
            ++c[i][x];
        }
    }
    
    // Read output: number of operations
    int cnt = ouf.readInt();
    if (cnt < 0 || cnt > n * n * 2) {
        quitf(_wa, "Operation number out of range: %d (expected 0 to %d)", cnt, n * n * 2);
    }
    int num = cnt;
    
    // Simulate operations
    while (cnt--) {
        // Read one operation: n cards to pass
        for (int i = 1; i <= n; i++) {
            a[i] = ouf.readInt();
            if (a[i] < 1 || a[i] > n) {
                quitf(_wa, "Card number out of range: %d (expected 1 to %d)", a[i], n);
            }
            if (!c[i][a[i]]) {
                quitf(_wa, "Player %d does not have card %d to pass", i, a[i]);
            }
            --c[i][a[i]];
        }
        // Pass cards to the right (player i passes to player (i % n) + 1)
        for (int i = 1; i <= n; i++) {
            ++c[i % n + 1][a[i]];
        }
    }
    
    // Verify final state: each player i should have exactly n cards with number i
    for (int i = 1; i <= n; i++) {
        if (c[i][i] != n) {
            quitf(_wa, "Player %d does not have exactly %d cards with number %d (has %d)", i, n, i, c[i][i]);
        }
    }
    
    // Calculate score based on number of operations
    // According to the problem solution:
    // - Optimal solution: at most n*(n-1)/2 operations for each part = n*n - n total
    // - Perfect score threshold: n*n/2 (half of maximum)
    // - Maximum acceptable: n*n - n
    double base_score = n * n - n;  // Maximum operations from solution
    double perfect = n * n / 2.0;   // Perfect score threshold
    
    double score_ratio;
    if (num <= perfect) {
        score_ratio = 1.0;  // Perfect or better solution
    } else if (num > base_score) {
        score_ratio = 0.0;  // Exceeds maximum acceptable operations
    } else {
        // Linear interpolation between perfect and base_score
        // Score decreases from 1.0 to 0.5 as operations increase from perfect to base_score
        score_ratio = max(0.5, (base_score - 1.0 * num) / (base_score - perfect));
    }
    
    // Ensure score is in [0.0, 1.0]
    score_ratio = max(0.0, min(1.0, score_ratio));
    double unbounded_ratio = score_ratio;
    
    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", num, score_ratio, unbounded_ratio);
    
    return 0;
}
