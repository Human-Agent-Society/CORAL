#include "testlib.h"
#include <vector>
#include <numeric>
#include <algorithm>

int main(int argc, char* argv[]) {
    // Initialize the interactor.
    // inf = test case input (.in), visible to contestant
    // ouf = contestant's output stream
    // ans = secret answer file (.ans), hidden from contestant
    registerInteraction(argc, argv);

    // Read public n from .in file
    int n = inf.readInt();

    // Read secret information from .ans file
    // The .ans file should now contain the best_queries value first, then the permutation.
    long long best_queries = ans.readLong();
    std::vector<int> hidden_permutation(n);
    for (int i = 0; i < n; ++i) {
        hidden_permutation[i] = ans.readInt();
    }

    // Send public n to contestant
    println(n);

    const int MAX_QUERIES_BASELINE = 10000;
    int query_count = 0;

    while (true) {
        int action_type = ouf.readInt();

        if (action_type == 0) { // Query
            if (++query_count > MAX_QUERIES_BASELINE) {
                // Use quitp to ensure a ratio is always available to the judge
                quitp(0.0, "Query limit exceeded. Max queries: %d. Ratio: 0.0000", MAX_QUERIES_BASELINE);
            }

            std::vector<int> query_sequence(n);
            for (int i = 0; i < n; ++i) {
                query_sequence[i] = ouf.readInt();
                if (query_sequence[i] < 1 || query_sequence[i] > n) {
                    quitf(_wa, "Invalid query: element %d is out of range [1, %d]", query_sequence[i], n);
                }
            }

            int matches = 0;
            for (int i = 0; i < n; ++i) {
                if (query_sequence[i] == hidden_permutation[i]) {
                    matches++;
                }
            }
            println(matches);

        } else if (action_type == 1) { // Final guess
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

            if (guess_permutation == hidden_permutation) {
                long long your_queries = query_count;

                if (your_queries >= MAX_QUERIES_BASELINE) {
                    quitp(0.0, "Correct guess, but not fewer than %lld queries. Queries: %lld. Ratio: 0.0000", MAX_QUERIES_BASELINE, your_queries);
                }

                // The "value" in the formula is how many queries you were *under* the baseline.
                double your_value = (double)(MAX_QUERIES_BASELINE - your_queries);
                double best_value = (double)(MAX_QUERIES_BASELINE - best_queries);
                
                // Avoid division by zero if the pre-calculated best is same or worse than baseline
                if (best_value <= 0) {
                     quitp(1.0, "Correct guess with %lld queries. Exceeded expectations. Ratio: 1.0000", your_queries);
                }

                double score_ratio = your_value / best_value;
                score_ratio = std::max(0.0, std::min(1.0, score_ratio)); // Clamp
                double unbounded_score_ratio = your_value / best_value; // No clamping for unbounded score
                
                quitp(score_ratio, "Correct guess in %lld queries. Ratio: %.4f, RatioUnbounded: %.4f", your_queries, score_ratio, unbounded_score_ratio);
            } else {
                quitp(0.0, "Wrong guess. Ratio: 0.0000");
            }
            break;

        } else {
            quitf(_wa, "Invalid action type: expected 0 or 1, but got %d", action_type);
        }
    }

    return 0;
}

