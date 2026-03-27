#include<bits/stdc++.h>
#include "testlib.h"
using namespace std;

int n, m, ref_ops;
vector<vector<int>> initial_poles;
vector<vector<int>> current_poles;

bool isValidFinalState() {
    // Check if all balls of same color are on the same pole
    map<int, int> color_to_pole; // color -> pole number (or -1 if not yet seen)
    
    for (int i = 0; i <= n; i++) {
        set<int> colors_on_pole;
        for (int ball : current_poles[i]) {
            colors_on_pole.insert(ball);
            
            if (color_to_pole.find(ball) == color_to_pole.end()) {
                color_to_pole[ball] = i;
            } else if (color_to_pole[ball] != i) {
                // Same color on different poles
                return false;
            }
        }
        
        // Check that each pole has at most one color
        if (colors_on_pole.size() > 1) {
            return false;
        }
    }
    
    return true;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input
    n = inf.readInt();
    m = inf.readInt();
    
    initial_poles.resize(n + 1);
    for (int i = 0; i < n; i++) {
        initial_poles[i].resize(m);
        for (int j = 0; j < m; j++) {
            initial_poles[i][j] = inf.readInt();
            if (initial_poles[i][j] < 1 || initial_poles[i][j] > n) {
                quitf(_fail, "Invalid color at pole %d: %d", i+1, initial_poles[i][j]);
            }
        }
    }
    
    // Read reference answer
    ref_ops = ans.readInt();
    
    // Initialize current state
    current_poles = initial_poles;
    
    // Read participant's output
    if (ouf.seekEof()) {
        quitf(_wa, "No output provided");
    }
    
    int participant_ops = ouf.readInt();
    
    if (participant_ops < 0) {
        quitf(_wa, "Number of operations cannot be negative: %d", participant_ops);
    }
    
    if (participant_ops > 2000000) {
        quitf(_wa, "Number of operations exceeds limit: %d > 2,000,000", participant_ops);
    }
    
    // Simulate operations
    for (int op = 0; op < participant_ops; op++) {
        if (ouf.seekEof()) {
            quitf(_wa, "Expected %d operations, but only found %d", participant_ops, op);
        }
        
        int x = ouf.readInt();
        int y = ouf.readInt();
        
        // Validate operation
        if (x < 1 || x > n + 1 || y < 1 || y > n + 1) {
            quitf(_wa, "Invalid operation %d: must be between 1 and %d", op+1, n+1);
        }
        
        if (x == y) {
            quitf(_wa, "Invalid operation %d: x and y must be different", op+1);
        }
        
        // Convert to 0-indexed
        x--; y--;
        
        // Check if pole x has at least one ball
        if (current_poles[x].empty()) {
            quitf(_wa, "Invalid operation %d: pole %d has no balls", op+1, x+1);
        }
        
        // Check if pole y has at most m-1 balls
        if ((int)current_poles[y].size() >= m) {
            quitf(_wa, "Invalid operation %d: pole %d is full", op+1, y+1);
        }
        
        // Perform the operation
        int ball = current_poles[x].back();
        current_poles[x].pop_back();
        current_poles[y].push_back(ball);
    }
    
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output found after %d operations", participant_ops);
    }
    
    // Check final state
    if (!isValidFinalState()) {
        quitf(_wa, "Final state is invalid: not all balls of same color are grouped");
    }
    
    // Calculate score
    double score_ratio = (double)(ref_ops + 1) / (participant_ops + 1);
    double unbounded_ratio = score_ratio;
    score_ratio = min(1.0, score_ratio);
    
    quitp(score_ratio, "Operations: %d. Ratio: %.6f, RatioUnbounded: %.6f", participant_ops, score_ratio, unbounded_ratio);
    
    return 0;
}