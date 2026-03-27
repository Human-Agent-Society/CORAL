#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    long long n = inf.readLong();
    long long m = inf.readLong();
    vector<vector<long long>> stacks(m);
    long long h = n / m;
    for (long long i = 0; i < m; ++i) {
        stacks[i].resize(h);
        for (long long j = 0; j < h; ++j) {
            stacks[i][j] = inf.readLong(1, n);
        }
    }

    // Read output
    vector<pair<long long, long long>> ops;
    while (!ouf.seekEof()) {
        long long v = ouf.readLong(1, n);
        long long to = ouf.readLong(0, m);
        ops.emplace_back(v, to);
        if ((int)ops.size() > 5000) {
            quitf(_wa, "Too many output");
        }
    }

    // Simulate
    long long cost = 0;
    long long t = 0; // number of boxes taken out
    for (auto [v, to] : ops) {
        // Find box v
        long long fi = -1, fj = -1;
        for (long long i = 0; i < m; ++i) {
            for (long long j = 0; j < (long long)stacks[i].size(); ++j) {
                if (stacks[i][j] == v) {
                    fi = i;
                    fj = j;
                    break;
                }
            }
            if (fi != -1) break;
        }
        if (fi == -1) {
            quitf(_wa, "Box %lld has already been taken out.", v);
        }

        if (to == 0) {
            // Operation 2: carry out box v
            if (fj + 1 != (long long)stacks[fi].size()) {
                quitf(_wa, "Box %lld is not at the top of the stack.", v);
            }
            if (v != t + 1) {
                quitf(_wa, "Before carrying out box %lld, all boxes less than %lld must be carried out.", v, v);
            }
            stacks[fi].pop_back();
            ++t;
        } else {
            // Operation 1: move v and above to stack 'to'
            long long len = (long long)stacks[fi].size();
            cost += (len - fj) + 1; // k + 1, where k = len - fj

            long long toidx = to - 1; // convert to 0-based
            if (fi != toidx) {
                // move segment [fj, len)
                auto &src = stacks[fi];
                auto &dst = stacks[toidx];
                for (long long k = fj; k < len; ++k) dst.push_back(src[k]);
                src.resize(fj);
            }
            // if fi == toidx, nothing changes but energy is still expended
        }
    }

    if (t < n) {
        quitf(_wa, "Not finished (%lld / %lld)", t, n);
    }

    long long score = 10000 - cost;
    if (score < 1) score = 1;
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}