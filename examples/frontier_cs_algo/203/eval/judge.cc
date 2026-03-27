#include "testlib.h"
#include <vector>
#include <set>

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    
    // Read N from .in file (public information)
    int N = inf.readInt();
    int total = 2 * N;
    
    // Read secret information from .ans file
    // gender[i]: 0 for X, 1 for Y
    std::vector<int> gender(total);
    for (int i = 0; i < total; ++i) {
        gender[i] = ans.readInt();
    }
    
    // original_color[i]: color ID (1 to N)
    std::vector<int> original_color(total);
    for (int i = 0; i < total; ++i) {
        original_color[i] = ans.readInt();
    }
    
    // loves[i]: the chameleon that chameleon i loves (1-indexed)
    std::vector<int> loves(total);
    for (int i = 0; i < total; ++i) {
        loves[i] = ans.readInt();
    }
    
    // Send N to contestant
    std::cout << N << std::endl;
    std::cout.flush();
    
    const int MAX_QUERIES = 20000;
    const int PERFECT_QUERIES = 4000;
    int query_count = 0;
    int answer_count = 0;
    
    std::set<std::pair<int, int>> answered_pairs;
    
    while (true) {
        std::string action = ouf.readToken();
        
        if (action == "Query") {
            if (++query_count > MAX_QUERIES) {
                quitp(0.0, "Query limit exceeded. Max queries: %d. Score: 0.0000", MAX_QUERIES);
            }
            
            int k = ouf.readInt();
            if (k < 1 || k > total) {
                quitf(_wa, "Invalid query size: %d (must be between 1 and %d)", k, total);
            }
            
            std::vector<int> meeting(k);
            std::set<int> meeting_set;
            
            for (int i = 0; i < k; ++i) {
                meeting[i] = ouf.readInt();
                if (meeting[i] < 1 || meeting[i] > total) {
                    quitf(_wa, "Invalid chameleon ID: %d (must be between 1 and %d)", meeting[i], total);
                }
                if (meeting_set.count(meeting[i])) {
                    quitf(_wa, "Duplicate chameleon %d in query", meeting[i]);
                }
                meeting_set.insert(meeting[i]);
            }
            
            // Calculate displayed colors
            std::set<int> displayed_colors;
            for (int s : meeting) {
                int loved = loves[s - 1]; // loves is 1-indexed
                
                // Check if the chameleon that s loves is also in the meeting
                if (meeting_set.count(loved)) {
                    // Display the original color of the loved one
                    displayed_colors.insert(original_color[loved - 1]);
                } else {
                    // Display own original color
                    displayed_colors.insert(original_color[s - 1]);
                }
            }
            
            std::cout << displayed_colors.size() << std::endl;
            std::cout.flush();
            
        } else if (action == "Answer") {
            int a = ouf.readInt();
            int b = ouf.readInt();
            
            if (a < 1 || a > total || b < 1 || b > total) {
                quitf(_wa, "Invalid chameleon IDs in answer: %d, %d", a, b);
            }
            
            if (a == b) {
                quitf(_wa, "Cannot pair a chameleon with itself: %d", a);
            }
            
            // Normalize pair order
            if (a > b) std::swap(a, b);
            
            if (answered_pairs.count({a, b})) {
                quitf(_wa, "Duplicate answer for pair (%d, %d)", a, b);
            }
            
            // Check if they have the same original color
            if (original_color[a - 1] != original_color[b - 1]) {
                quitf(_wa, "Wrong answer: chameleons %d and %d do not have the same original color", a, b);
            }
            
            answered_pairs.insert({a, b});
            answer_count++;
            
            if (answer_count == N) {
                // All pairs answered, calculate score
                long long Q = query_count;
                long long score_value = MAX_QUERIES - Q;
                
                if (Q > MAX_QUERIES) {
                    quitp(0.0, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", (long long)0, 0.0, 0.0);
                }
                
                // Unbounded ratio (can exceed 1.0)
                double final_unbounded_ratio = (double)(MAX_QUERIES - Q) / (double)(MAX_QUERIES - PERFECT_QUERIES);
                final_unbounded_ratio = std::max(0.0, final_unbounded_ratio);
                
                // Bounded ratio for scoring (capped at 1.0)
                double final_ratio = std::min(1.0, final_unbounded_ratio);
                
                quitp(final_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score_value, final_ratio, final_unbounded_ratio);
            }
            
        } else {
            quitf(_wa, "Invalid action: expected 'Query' or 'Answer', but got '%s'", action.c_str());
        }
    }
    
    return 0;
}
