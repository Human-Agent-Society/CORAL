#include "testlib.h"
#include <vector>
#include <set>
#include <string>

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read both n and hidden permutation from .in file
    int n = inf.readInt();
    std::vector<int> hidden_permutation(n);
    for (int i = 0; i < n; ++i) {
        hidden_permutation[i] = inf.readInt();
    }

    // Read reference queries from .ans file (just one number)
    long long ref_queries = ans.readLong();

    // Send only n to contestant
    println(n);

    int query_count = 0;

    while (true) {
        // Use readToken() instead of readChar() to properly skip whitespace
        std::string action_str = ouf.readToken();
        
        if (action_str.empty()) {
            quitf(_wa, "Expected '?' or '!', but got empty input");
        }
        
        char action_type = action_str[0];
        
        if (action_type == '?') { // Query
            query_count++;
            
            int k = ouf.readInt();
            if (k < 1 || k > n) {
                quitf(_wa, "Invalid query: k=%d is out of range [1, %d]", k, n);
            }
            
            std::vector<int> positions(k);
            std::set<int> position_set;
            
            for (int i = 0; i < k; ++i) {
                positions[i] = ouf.readInt();
                if (positions[i] < 1 || positions[i] > n) {
                    quitf(_wa, "Invalid query: position %d is out of range [1, %d]", positions[i], n);
                }
                if (position_set.count(positions[i])) {
                    quitf(_wa, "Invalid query: duplicate position %d", positions[i]);
                }
                position_set.insert(positions[i]);
            }
            
            // Calculate sum and check if average is integer
            long long sum = 0;
            for (int pos : positions) {
                sum += hidden_permutation[pos - 1];
            }
            
            int answer = (sum % k == 0) ? 1 : 0;
            println(answer);
            
        } else if (action_type == '!') { // Final guess
            std::vector<int> guess_permutation(n);
            std::vector<bool> seen(n + 1, false);
            bool is_valid_permutation = true;
            
            for (int i = 0; i < n; ++i) {
                guess_permutation[i] = ouf.readInt();
                if (guess_permutation[i] < 1 || guess_permutation[i] > n || seen[guess_permutation[i]]) {
                    is_valid_permutation = false;
                }
                seen[guess_permutation[i]] = true;
            }
            
            if (!is_valid_permutation) {
                quitf(_wa, "Invalid final guess: the sequence is not a valid permutation.");
            }
            
            // Check constraint p1 <= n/2
            if (guess_permutation[0] > n / 2) {
                quitf(_wa, "Invalid final guess: p1=%d must be <= n/2=%d", guess_permutation[0], n / 2);
            }
            
            // Check if guess matches hidden permutation or its complement
            bool matches = true;
            bool matches_complement = true;
            
            for (int i = 0; i < n; ++i) {
                if (guess_permutation[i] != hidden_permutation[i]) {
                    matches = false;
                }
                if (guess_permutation[i] != n + 1 - hidden_permutation[i]) {
                    matches_complement = false;
                }
            }
            
            if (!matches && !matches_complement) {
                quitp(0.0, "Wrong guess. Queries used: %d. Ratio: 0.0000", query_count);
            } else {
                long long your_queries = query_count;
                double score_ratio = (double)(ref_queries + 1) / (your_queries + 1);
                if (score_ratio < 0.0) score_ratio = 0.0;
                double unbounded_ratio = std::max(0.0, score_ratio);
                score_ratio = std::min(1.0, score_ratio);
                
                quitp(score_ratio, "Correct guess in %lld queries. Ratio: %.4f, RatioUnbounded: %.4f", your_queries, score_ratio, unbounded_ratio);
            }
            break;
            
        } else {
            quitf(_wa, "Invalid action type: expected '?' or '!', but got '%c'", action_type);
        }
    }

    return 0;
}