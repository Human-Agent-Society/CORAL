#include "testlib.h"
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <cctype>

using namespace std;

// Apply operation: choose indices (i, j) with 1 <= i < j <= n
// Replace A_i with A_j - 1 and A_j with A_i + 1
void apply_op(vector<int>& a, int i, int j) {
    int u = i - 1;  // Convert to 0-based index
    int v = j - 1;  // Convert to 0-based index
    int old_ai = a[u];
    int old_aj = a[v];
    a[u] = old_aj - 1;
    a[v] = old_ai + 1;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input
    int n = inf.readInt();
    vector<int> initial_a = inf.readInts(n);
    vector<int> target_b = inf.readInts(n);
    
    // Read user and standard output: first token should be "Yes" or "No"
    string user_token = ouf.readToken();
    string std_token = ans.readToken();
    
    // Convert to uppercase for case-insensitive comparison
    string user_upper = user_token;
    string std_upper = std_token;
    for (char &c : user_upper) c = toupper(c);
    for (char &c : std_upper) c = toupper(c);
    
    // Validate user output format
    if (user_upper != "YES" && user_upper != "NO") {
        double score_ratio = 0.0;
        double unbounded_ratio = 0.0;
        quitp(score_ratio, "Value: 0. Ratio: %.4f, RatioUnbounded: %.4f. Output must start with 'Yes' or 'No', found '%s'", 
              score_ratio, unbounded_ratio, user_token.c_str());
    }
    
    bool user_possible = (user_upper == "YES");
    bool std_possible = (std_upper == "YES");
    
    // Check if user's answer matches standard answer
    if (!user_possible && std_possible) {
        double score_ratio = 0.0;
        double unbounded_ratio = 0.0;
        quitp(score_ratio, "Value: 0. Ratio: %.4f, RatioUnbounded: %.4f. Participant found no solution, but solution exists.", 
              score_ratio, unbounded_ratio);
    }
    
    if (user_possible && !std_possible) {
        double score_ratio = 0.0;
        double unbounded_ratio = 0.0;
        quitp(score_ratio, "Value: 0. Ratio: %.4f, RatioUnbounded: %.4f. Participant claims 'Yes' but standard answer is 'No'.", 
              score_ratio, unbounded_ratio);
    }
    
    // If both say "No", it's correct
    if (!user_possible && !std_possible) {
        double score_ratio = 1.0;
        double unbounded_ratio = 1.0;
        quitp(score_ratio, "Value: 0. Ratio: %.4f, RatioUnbounded: %.4f. Correct result: No solution.", 
              score_ratio, unbounded_ratio);
    }
    
    // Both say "Yes", now check the operation sequence
    int m_std = ans.readInt();  // Standard answer: number of operations
    int m_user = ouf.readInt();  // User answer: number of operations
    
    vector<int> current_a = initial_a;
    
    // Simulate user's operations
    for (int k = 0; k < m_user; k++) {
        int i = ouf.readInt();
        int j = ouf.readInt();
        
        // Validate operation indices
        if (i < 1 || i > n || j < 1 || j > n) {
            double score_ratio = 0.0;
            double unbounded_ratio = 0.0;
            quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Operation %d: indices (%d, %d) out of bounds [1, %d]", 
                  m_user, score_ratio, unbounded_ratio, k + 1, i, j, n);
        }
        
        if (i >= j) {
            double score_ratio = 0.0;
            double unbounded_ratio = 0.0;
            quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Operation %d: indices (%d, %d) do not satisfy i < j", 
                  m_user, score_ratio, unbounded_ratio, k + 1, i, j);
        }
        
        apply_op(current_a, i, j);
    }
    
    // Check if final sequence matches target
    if (current_a != target_b) {
        double score_ratio = 0.0;
        double unbounded_ratio = 0.0;
        quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Final sequence does not match target B.", 
              m_user, score_ratio, unbounded_ratio);
    }
    
    // Calculate score based on number of operations
    // Scoring rules:
    // - If m_user <= m_std: full score (1.0)
    // - If m_user > 2 * m_std: zero score (0.0)
    // - Otherwise: linear interpolation: score = (2 * m_std - m_user) / m_std
    double score_ratio;
    double unbounded_ratio;
    
    if (m_user <= m_std) {
        score_ratio = 1.0;  // Perfect or better than standard
        unbounded_ratio = 1.0;
    } else if (m_user > 2 * m_std) {
        score_ratio = 0.0;  // Exceeds maximum acceptable operations
        unbounded_ratio = 0.0;
    } else {
        // Linear decrease from 1.0 to 0.0 as operations increase from m_std to 2*m_std
        score_ratio = (double)(2 * m_std - m_user) / (double)m_std;
        unbounded_ratio = score_ratio;
    }
    
    // Ensure score is in [0.0, 1.0]
    score_ratio = max(0.0, min(1.0, score_ratio));
    unbounded_ratio = max(0.0, min(1.0, unbounded_ratio));
    
    // Use standard quitp format
    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", m_user, score_ratio, unbounded_ratio);
    
    return 0;
}
