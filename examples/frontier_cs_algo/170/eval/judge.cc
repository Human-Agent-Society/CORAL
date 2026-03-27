#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    long long n = inf.readLong();
    long long l = inf.readLong();
    vector<long long> T = inf.readLongs((int)n);

    // Read output pairs until EOF
    vector<pair<long long, long long>> out;
    while (!ouf.seekEof()) {
        long long a = ouf.readLong(0, n - 1);
        long long b = ouf.readLong(0, n - 1);
        out.emplace_back(a, b);
    }

    if ((long long)out.size() != n) {
        quitf(_wa, "Number of pairs in output is not N");
    }

    // Simulation
    vector<long long> counts(n, 0);
    long long pos = 0;
    for (long long step = 0; step < l; ++step) {
        long long a = out[pos].first;
        long long b = out[pos].second;
        counts[pos] += 1;
        if (counts[pos] % 2 == 1) pos = a;
        else pos = b;
    }

    // Score calculation: score = 2 * L - sum |counts[i] - T[i]|
    long long score = 2LL * l;
    for (long long i = 0; i < n; ++i) {
        long long diff = counts[i] - T[i];
        score -= llabs(diff);
    }

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}