// interactor.cpp
// Build: g++ -std=gnu++17 -O2 -pipe -static -s interactor.cpp -o interactor
// Run  : interactor <input> <output> <answer> [--seed=...]
// input: one line "n s"
// Protocol:
//   - Player output: walk x (0 <= x <= 1e9) -- Interactor responds: label[pos]
//   - Player output: guess g -- Terminates; if g==n then score by q, otherwise score 0
//
// Rules:
//   - Initial: label[s]=s, used set = {s}
//   - When walking to position pos that hasn't been assigned: repeatedly random r in [1..n] until r not in used, then label[pos]=r, add r to used
//   - Maximum walk count MAX_Q=200000
//
// Scoring: f(q) is log10 space piecewise linear interpolation:
//   (1,100), (10000,95), (20000,60), (50000,30), extrapolated to 0 at 200000
//   Correct: quitp(f/100), wrong: quitp(0)

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const long long MAX_Q = 200000LL;

// Continuous, monotonically decreasing, log10 piecewise linear interpolation
static double score_from_queries(long long q) {
    if (q <= 1) return 100.0;

    const double t  = log10((double)q);
    const double t1 = 0.0;                   // log10(1)
    const double t2 = 4.0;                   // log10(10000)
    const double t3 = log10(20000.0);        // ~4.30103
    const double t4 = log10(50000.0);        // ~4.69897
    const double t5 = log10(200000.0);       // ~5.30103

    auto lerp = [](double a, double b, double x, double xa, double xb) {
        if (xa == xb) return a;
        double w = (x - xa) / (xb - xa);
        return a + (b - a) * w;
    };

    if (t <= t2)          return lerp(100.0, 95.0, t, t1, t2);
    else if (t <= t3)     return lerp(95.0,  60.0, t, t2, t3);
    else if (t <= t4)     return lerp(60.0,  30.0, t, t3, t4);
    else if (t <= t5)     return max(0.0, lerp(30.0,   0.0, t, t4, t5));
    else                  return 0.0;
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read n, s
    long long n = inf.readLong(1LL, 1000000000LL, "n");
    long long s = inf.readLong(1LL, n,            "s");

    long long pos  = s;
    long long qcnt = 0;

    // Node -> visible value; assigned only on first visit to node
    unordered_map<long long, long long> label;
    label.reserve(1 << 16);
    label.max_load_factor(0.7f);

    // Set of used numbers to avoid duplicates
    unordered_set<long long> used;
    used.reserve(1 << 16);
    used.max_load_factor(0.7f);

    // Initialize
    label[s] = s;
    used.insert(s);

    // Sample an unused random number (n is large, expected attempts is low)
    auto take_random_unused_number = [&]() -> long long {
        while (true) {
            long long r = rnd.next(1LL, n);
            if (!used.count(r)) {
                used.insert(r);
                return r;
            }
        }
    };

    auto tell = [&](long long v) {
        cout << v << '\n' << flush;
    };

    while (true) {
        string cmd = ouf.readWord();  // Read a word (non-whitespace characters)


        if (cmd == "walk") {
            long long x = ouf.readLong(0LL, 1000000000LL, "x");
            // cerr<<x<<"\n";
            long long step = (n == 1 ? 0 : (x % n));
            pos = ((pos - 1 + step) % n) + 1;

            if (!label.count(pos)) {
                long long val = take_random_unused_number();
                label[pos] = val;
            }

            ++qcnt;
            if (qcnt > MAX_Q) {
                quitf(_wa, "Too many queries: %lld (max %lld)", qcnt, MAX_Q);
            }

            tell(label[pos]);

        } else if (cmd == "guess") {
            long long g = ouf.readLong(1LL, 1000000000LL, "n_guess");
            bool ok = (g == n);

            if (!ok) {
                quitp(0.0, "Wrong answer. hidden n=%lld, your guess=%lld, queries=%lld", n, g, qcnt);
            } else {
                double score = score_from_queries(qcnt);
                double part  = max(0.0, min(100.0, score)) / 100.0;
                double unbounded_part = max(0.0, score) / 100.0;
                
                quitp(part, "OK. n=%lld, queries=%lld, Ratio: %.4f, RatioUnbounded: %.4f", n, qcnt, part, unbounded_part);
            }

        } else {
            quitf(_wa, "Unknown command: '%s' (expected 'walk' or 'guess')", cmd.c_str());
        }
    }
}
