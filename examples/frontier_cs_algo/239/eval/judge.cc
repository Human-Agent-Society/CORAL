#include "testlib.h"
#include <iostream>
#include <vector>
#include <queue>
#include <algorithm>

using namespace std;

const int MAXN = (1 << 12) + 10;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input: n vertices (0 to n)
    int n = inf.readInt();
    if (n < 0 || n > (1 << 12)) {
        quitf(_fail, "Invalid input: n = %d (expected 0 to %d)", n, 1 << 12);
    }
    
    // Read answer: optimal number of edges
    int mans = ans.readInt();
    
    // Read output: number of edges added
    int mout = ouf.readInt();
    if (mout < 0) {
        quitf(_wa, "Invalid output: number of edges %d is negative", mout);
    }
    
    // Initialize graph: initially contains edges i -> i+1 for i = 0 to n-1
    vector<vector<int>> G(n + 1, vector<int>(n + 1, 0));
    for (int i = 0; i < n; ++i) {
        G[i][i + 1] = 1;
    }
    
    // Process each edge addition
    for (int i = 1; i <= mout; ++i) {
        int a = ouf.readInt();
        int b = ouf.readInt();
        int c = ouf.readInt();
        
        // Validate vertex indices
        if (a < 0 || a > n || b < 0 || b > n || c < 0 || c > n) {
            quitf(_wa, "Invalid vertex index in edge %d: (%d, %d, %d) (expected 0 to %d)", i, a, b, c, n);
        }
        
        // Check if edges a->b and b->c exist
        if (!G[a][b] || !G[b][c]) {
            quitf(_wa, "Cannot add edge %d->%d: edges %d->%d and %d->%d must both exist", a, c, a, b, b, c);
        }
        
        // Add edge a->c
        G[a][c] = 1;
    }
    
    // Verify that for every pair (i, j) with i < j, there exists a path of at most 3 edges
    vector<int> d(n + 1);
    for (int i = 0; i <= n; ++i) {
        // BFS from vertex i
        queue<int> q;
        q.push(i);
        fill(d.begin(), d.end(), -1);
        d[i] = 0;
        
        while (!q.empty()) {
            int x = q.front();
            q.pop();
            
            for (int v = x + 1; v <= n; ++v) {
                if (G[x][v] && d[v] == -1) {
                    d[v] = d[x] + 1;
                    q.push(v);
                }
            }
        }
        
        // Check distances to all vertices j > i
        for (int j = i + 1; j <= n; ++j) {
            if (d[j] == -1 || d[j] > 3) {
                quitf(_wa, "Distance from vertex %d to vertex %d is %d (expected at most 3)", i, j, d[j] == -1 ? -1 : d[j]);
            }
        }
    }
    
    // Calculate score based on number of edges
    // According to the problem statement:
    // - If mout <= mans, score = 1.0 (full score)
    // - If mout > 3 * mans, score = 0.0
    // - Otherwise, score decreases linearly from 1.0 to 0.0
    double score_ratio;
    if (mout <= mans) {
        score_ratio = 1.0;  // Full score for optimal or better solution
    } else if (mout > 3 * mans) {
        score_ratio = 0.0;  // Zero score if exceeds 3 * mans
    } else {
        // Linear decrease: when mout = mans, score = 1.0; when mout = 3*mans, score = 0.0
        // Formula: score = (3*mans - mout) / (3*mans - mans) = (3*mans - mout) / (2*mans)
        score_ratio = (3.0 * mans - mout) / (2.0 * mans);
    }
    
    // Ensure score is in [0.0, 1.0]
    score_ratio = max(0.0, min(1.0, score_ratio));
    double unbounded_ratio = score_ratio;
    
    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", mout, score_ratio, unbounded_ratio);
    
    return 0;
}