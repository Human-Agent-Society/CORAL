#include "testlib.h"
#include <vector>
#include <algorithm>

using namespace std;

static const long long N = 30;
static const long long N2 = N * (N + 1) / 2;

static inline bool is_adj(long long x1, long long y1, long long x2, long long y2) {
    if (x1 == x2) return (y1 + 1 == y2) || (y2 + 1 == y1);
    if (x1 + 1 == x2) return (y1 == y2) || (y1 + 1 == y2);
    if (x2 + 1 == x1) return (y2 == y1) || (y2 + 1 == y1);
    return false;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    vector<vector<long long>> bs(N);
    for (long long i = 0; i < N; i++) {
        bs[i].resize(i + 1);
        for (long long j = 0; j <= i; j++) {
            bs[i][j] = inf.readInt(0, (int)N2 - 1, "b");
        }
    }

    // Read output
    long long K = ouf.readInt(0, 10000, "K");
    for (long long t = 0; t < K; t++) {
        long long x1 = ouf.readInt(0, (int)N - 1, "x1");
        long long y1 = ouf.readInt(0, (int)x1, "y1");
        long long x2 = ouf.readInt(0, (int)N - 1, "x2");
        long long y2 = ouf.readInt(0, (int)x2, "y2");
        if (!is_adj(x1, y1, x2, y2)) {
            quitf(_wa, "(%lld, %lld) and (%lld, %lld) are not adjacent (turn %lld)", x1, y1, x2, y2, t);
        }
        swap(bs[x1][y1], bs[x2][y2]);
    }
    if (!ouf.seekEof()) {
        quitf(_wa, "Too many output");
    }

    // Compute E
    long long E = 0;
    for (long long x = 0; x < N - 1; x++) {
        for (long long y = 0; y <= x; y++) {
            if (bs[x][y] > bs[x + 1][y]) E++;
            if (bs[x][y] > bs[x + 1][y + 1]) E++;
        }
    }

    // Compute score
    long long score;
    if (E == 0) {
        score = 50000 + 5 * (10000 - K);
    } else {
        score = 50000 - 50 * E;
    }

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}