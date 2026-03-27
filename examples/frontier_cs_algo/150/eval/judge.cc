#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int DIRS[2][2] = {{0,1},{1,0}};

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    long long N = inf.readLong();
    long long M = inf.readLong();
    vector<string> s(M);
    for (long long i = 0; i < M; i++) {
        s[i] = inf.readToken();
    }

    // Read output matrix
    vector<string> out(N);
    for (long long i = 0; i < N; i++) {
        out[i] = ouf.readToken();
    }
    if (!ouf.seekEof()) {
        quitf(_wa, "Too many lines");
    }

    // Validate output matrix
    long long dotCount = 0;
    for (long long i = 0; i < N; i++) {
        if ((long long)out[i].size() != N) {
            quitf(_wa, "illegal length: %lld", (long long)out[i].size());
        }
        for (long long j = 0; j < N; j++) {
            char c = out[i][j];
            if (!((c >= 'A' && c <= 'H') || c == '.')) {
                quitf(_wa, "illegal char: %c", c);
            }
            if (c == '.') dotCount++;
        }
    }

    auto is_substring = [&](const vector<string>& a, const string& b, long long i, long long j, int d) -> bool {
        int di = DIRS[d][0], dj = DIRS[d][1];
        for (long long k = 0; k < (long long)b.size(); k++) {
            long long ii = (i + di * k) % N;
            long long jj = (j + dj * k) % N;
            if (a[ii][jj] != b[(size_t)k]) return false;
        }
        return true;
    };

    // Compute c = number of strings that appear as a subsequence
    long long c = 0;
    for (long long idx = 0; idx < M; idx++) {
        bool used = false;
        for (long long i = 0; i < N && !used; i++) {
            for (long long j = 0; j < N && !used; j++) {
                for (int d = 0; d < 2 && !used; d++) {
                    if (is_substring(out, s[idx], i, j, d)) {
                        used = true;
                    }
                }
            }
        }
        if (used) c++;
    }

    // Compute score
    double scoreD;
    if (c < M) {
        scoreD = 1e8 * (double)c / (double)M;
    } else {
        double twoNN = 2.0 * (double)N * (double)N;
        scoreD = 1e8 * twoNN / (twoNN - (double)dotCount);
    }
    long long score = llround(scoreD);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}