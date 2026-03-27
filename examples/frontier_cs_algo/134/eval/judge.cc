#include "testlib.h"
#include <vector>

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read n from .in file
    long long n = inf.readLong();

    // Read secret information from .ans file
    long long ref_queries = ans.readLong();
    long long hidden_a = ans.readLong();
    long long hidden_b = ans.readLong();

    // Validate hidden values
    if (hidden_a < 1 || hidden_a > n || hidden_b < 1 || hidden_b > n) {
        quitf(_fail, "Invalid hidden values in .ans file");
    }

    // Send n to contestant
    println(n);

    const int MAX_QUERIES = 10000;
    int query_count = 0;

    while (true) {
        query_count++;
        
        if (query_count > MAX_QUERIES) {
            quitp(0.0, "Query limit exceeded. Max queries: %d. Ratio: 0.0000", MAX_QUERIES);
        }

        long long x = ouf.readLong();
        long long y = ouf.readLong();

        // Validate query
        if (x < 1 || x > n || y < 1 || y > n) {
            quitf(_wa, "Invalid query: x and y must be in range [1, %lld]", n);
        }

        // Check if correct
        if (x == hidden_a && y == hidden_b) {
            println(0);
            
            // Calculate score: min((ref_queries + 1) / (your_queries + 1), 1)
            double score_ratio = (double)(ref_queries + 1) / (double)(query_count + 1);
            double unbounded_ratio = score_ratio;
            score_ratio = std::min(1.0, score_ratio);
            
            quitp(score_ratio, "Correct answer in %d queries. Ratio: %.4f, RatioUnbounded: %.4f", query_count, score_ratio, unbounded_ratio);
            break;
        }

        // Determine valid responses
        std::vector<int> valid_responses;
        
        if (x < hidden_a) {
            valid_responses.push_back(1);
        }
        if (y < hidden_b) {
            valid_responses.push_back(2);
        }
        if (x > hidden_a || y > hidden_b) {
            valid_responses.push_back(3);
        }

        // At least one response must be valid
        if (valid_responses.empty()) {
            // This shouldn't happen
            quitf(_fail, "Internal error: no valid response");
        }

        // Randomly choose one valid response
        int response = valid_responses[rnd.next(0, (int)valid_responses.size() - 1)];

        println(response);
    }

    return 0;
}