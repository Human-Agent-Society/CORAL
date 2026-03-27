#include "testlib.h"
#include <vector>
#include <algorithm>
#include <string>

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read n, l1, l2 from .in file (visible to contestant)
    int n = inf.readInt();
    int l1 = inf.readInt();  // Maximum allowed ask operations
    int l2 = inf.readInt();  // Maximum allowed swap operations

    // Read reference solution costs from .ans file
    int ref_s1 = ans.readInt();
    int ref_s2 = ans.readInt();
    
    // Read the hidden permutation from .in file
    std::vector<int> hidden_perm(n + 1);
    for (int i = 1; i <= n; ++i) {
        hidden_perm[i] = inf.readInt();
    }

    // Current state of the permutation (will be modified by swaps)
    std::vector<int> current_perm = hidden_perm;

    // Send n, l1, l2 to contestant
    println(n, l1, l2);

    int s1 = 0; // Count of ask operations
    int s2 = 0; // Count of swap operations

    // Helper function to count value-contiguous segments
    auto count_segments = [&](int l, int r) -> int {
        std::vector<bool> present(n + 1, false);
        int min_val = n + 1, max_val = 0;
        
        for (int i = l; i <= r; ++i) {
            present[current_perm[i]] = true;
            min_val = std::min(min_val, current_perm[i]);
            max_val = std::max(max_val, current_perm[i]);
        }
        
        // Count segments: a segment is a maximal contiguous range of present values
        int segments = 0;
        bool in_segment = false;
        for (int v = min_val; v <= max_val; ++v) {
            if (present[v]) {
                if (!in_segment) {
                    segments++;
                    in_segment = true;
                }
            } else {
                in_segment = false;
            }
        }
        return segments;
    };

    while (true) {
        int operation = ouf.readInt(1, 3);

        if (operation == 1) { // ask operation
            s1++;
            if (s1 > l1) {
                quitp(0.0, "Exceeded ask operation limit. Used %d, limit is %d. Ratio: 0.0000", s1, l1);
            }
            
            int l = ouf.readInt(1, n);
            int r = ouf.readInt(l, n);
            
            int result = count_segments(l, r);
            println(result);

        } else if (operation == 2) { // swp operation
            s2++;
            if (s2 > l2) {
                quitp(0.0, "Exceeded swap operation limit. Used %d, limit is %d. Ratio: 0.0000", s2, l2);
            }
            
            int i = ouf.readInt(1, n);
            int j = ouf.readInt(1, n);
            
            std::swap(current_perm[i], current_perm[j]);
            println(1);

        } else if (operation == 3) { // report operation
            std::vector<int> guess(n + 1);
            for (int i = 1; i <= n; ++i) {
                guess[i] = ouf.readInt(1, n);
            }

            // Check if it's a valid permutation
            std::vector<bool> seen(n + 1, false);
            bool valid = true;
            for (int i = 1; i <= n; ++i) {
                if (seen[guess[i]]) {
                    valid = false;
                    break;
                }
                seen[guess[i]] = true;
            }

            if (!valid) {
                quitp(0.0, "Invalid permutation in report. Ratio: 0.0000");
            }

            // Check if guess matches current_perm or its reverse
            bool matches_normal = true;
            bool matches_reverse = true;
            
            for (int i = 1; i <= n; ++i) {
                if (guess[i] != current_perm[i]) {
                    matches_normal = false;
                }
                if (guess[i] != (n - current_perm[i] + 1)) {
                    matches_reverse = false;
                }
            }

            if (!matches_normal && !matches_reverse) {
                quitp(0.0, "Wrong answer. s1=%d, s2=%d. Ratio: 0.0000", s1, s2);
            }

            // Calculate score
            double score_ratio = std::min(1.0, (double)(ref_s1 + ref_s2 + 1) / (double)(s1 + s2 + 1));
            double unbounded_ratio = (double)(ref_s1 + ref_s2 + 1) / (double)(s1 + s2 + 1);
            
            quitp(score_ratio, "Correct answer. s1=%d, s2=%d. Ratio: %.4f, RatioUnbounded: %.4f", s1, s2, score_ratio, unbounded_ratio);

        }
    }

    return 0;
}