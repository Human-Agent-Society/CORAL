#include "testlib.h"
#include <vector>
#include <numeric>
#include <algorithm>
using namespace std;

// Function to perform the swap operation on a permutation
void perform_operation(vector<int>& p, int x, int y) {
    int n = p.size();
    if (x <= 0 || y <= 0 || x + y >= n) {
        // This is an invalid operation, the checker will catch this.
        return;
    }
    vector<int> prefix(p.begin(), p.begin() + x);
    vector<int> middle(p.begin() + x, p.end() - y);
    vector<int> suffix(p.end() - y, p.end());
    p.clear();
    p.insert(p.end(), suffix.begin(), suffix.end());
    p.insert(p.end(), middle.begin(), middle.end());
    p.insert(p.end(), prefix.begin(), prefix.end());
}

bool check_sorted(vector <int> p) {
    for (int i = 0; i < p.size() - 1; i++) {
        if (p[i] > p[i + 1]) return false;
    }
    return true;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    int n = inf.readInt();
    vector<int> p(n);
    for (int i = 0; i < n; ++i) {
        p[i] = inf.readInt();
    }

    // int best_operations = ans.readInt();

    // Read contestant's output
    int m = ouf.readInt();
    if (m < 0 || m > 4 * n) {
        quitf(_wa, "Invalid number of operations m=%d. Must be between 0 and 4*n.", m);
    }

    vector<int> p_contestant = p;
    for (int i = 0; i < m; ++i) {
        int x = ouf.readInt();
        int y = ouf.readInt();
        if (x <= 0 || y <= 0 || x + y >= n) {
            quitf(_wa, "Invalid operation (x=%d, y=%d) for n=%d.", x, y, n);
        }
        perform_operation(p_contestant, x, y);
    }

    if (!check_sorted(p_contestant)) {
        quitf(_wa, "The final permutation is not the lexicographically smallest possible.");
    }

    // If we reach here, the permutation is correct. Now, calculate the score.
    int your_operations = m;
    int baseline_operations = 4 * n;
    int best_operations = 2 * n + 1;

    double ratio = 0, unbounded_ratio = 0;

    if (your_operations >= baseline_operations) {
        // Score is 0 if not better than baseline
        ratio = 0.0;
    } else {
        double your_value = (double)(baseline_operations - your_operations);
        double best_value = (double)(baseline_operations - best_operations);

        if (best_value <= 0) { // Avoid division by zero
            ratio = 1.0;
        } else {
            ratio = std::max(0.0, std::min(1.0, your_value / best_value)); // Clamp
            unbounded_ratio = std::max(0.0, your_value / best_value);
        }
    }

    quitp(ratio, "Final average score ratio. Ratio: %.4f, RatioUnbounded: %.4f", ratio, unbounded_ratio);
    return 0;
}
