#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

double compute_efficiency_value() {
    // Read input
    int N = inf.readInt();
    vector<int> S(N);
    for (int i = 0; i < N; i++) {
        S[i] = inf.readInt();
    }
    int M = inf.readInt();
    vector<pair<int, int>> ermek_swaps(M);
    for (int i = 0; i < M; i++) {
        ermek_swaps[i].first = inf.readInt();
        ermek_swaps[i].second = inf.readInt();
    }

    // Read output
    int R = ouf.readInt();
    if (R < 0 || R > M) {
        quitf(_wa, "Invalid R: %d (must be 0 <= R <= %d)", R, M);
    }

    vector<pair<int, int>> aizhan_swaps(R);
    for (int i = 0; i < R; i++) {
        aizhan_swaps[i].first = ouf.readInt();
        aizhan_swaps[i].second = ouf.readInt();
        if (aizhan_swaps[i].first < 0 || aizhan_swaps[i].first >= N ||
            aizhan_swaps[i].second < 0 || aizhan_swaps[i].second >= N) {
            quitf(_wa, "Invalid swap indices at round %d: (%d, %d)", 
                  i, aizhan_swaps[i].first, aizhan_swaps[i].second);
        }
    }

    long long output_V = ouf.readLong();

    // Simulate the game
    vector<int> current_S = S;
    long long total_cost = 0;

    for (int k = 0; k < R; k++) {
        // Ermek's move
        swap(current_S[ermek_swaps[k].first], current_S[ermek_swaps[k].second]);
        
        // Aizhan's move
        int u = aizhan_swaps[k].first;
        int v = aizhan_swaps[k].second;
        swap(current_S[u], current_S[v]);
        
        // Add cost
        total_cost += abs(u - v);
    }

    // Check if sorted
    for (int i = 0; i < N; i++) {
        if (current_S[i] != i) {
            quitf(_wa, "Array is not sorted after %d rounds. S[%d] = %d, expected %d", 
                  R, i, current_S[i], i);
        }
    }

    // Calculate efficiency value (using __int128 to handle overflow)
    __int128 V_128 = (__int128)R * total_cost;
    
    // Check if output V matches (compare with __int128)
    __int128 output_V_128 = output_V;
    if (V_128 != output_V_128) {
        // For printing, we need to handle __int128
        if (V_128 <= 9223372036854775807LL && output_V <= 9223372036854775807LL) {
            quitf(_wa, "Output V = %lld does not match computed V = %lld", output_V, (long long)V_128);
        } else {
            quitf(_wa, "Output V does not match computed V (values too large for display)");
        }
    }

    // Return as double to avoid overflow issues in scoring
    return (double)V_128;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    double V = compute_efficiency_value();
    double baseline_value = ans.readDouble();
    double best_value = ans.readDouble();

    // Score calculation based on problem statement
    // best_value = 10^13, baseline_value = 3.3×10^15
    const double BEST_THRESHOLD = 1e13;
    const double BASELINE_THRESHOLD = 3.3e15;
    
    double score;
    if (V <= BEST_THRESHOLD) {
        score = 100.0;
    } else if (V >= BASELINE_THRESHOLD) {
        score = 0.0;
    } else {
        score = 100.0 * (BASELINE_THRESHOLD - V) / (BASELINE_THRESHOLD - BEST_THRESHOLD);
    }

    // score_ratio: V越小越好，接近best_value得1分，接近baseline_value得0分
    double score_ratio = max(0.0, min(1.0, (baseline_value - V) / (baseline_value - best_value)));
    double unbounded_ratio = max(0.0, (baseline_value - V) / (baseline_value - best_value));
    
    quitp(score_ratio, "Value: %.2e. Score: %.2f. Ratio: %.4f, RatioUnbounded: %.4f", 
          V, score, score_ratio, unbounded_ratio);
}

