#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static inline double dist2D(long long xa, long long ya, long long xb, long long yb) {
    double dx = (double)xa - (double)xb;
    double dy = (double)ya - (double)yb;
    return hypot(dx, dy);
}

static inline double clamp01(double v) {
    if (v < 0.0) return 0.0;
    if (v > 1.0) return 1.0;
    return v;
}

// Piecewise linear visibility remap M: y = M(x)
// Anchors: (x -> y) pairs, x must be strictly increasing in [0,1]
static double remapVisibility(double x) {
    struct Pt { double x, y; };
    static const Pt A[] = {
        {0.00, 0.00},
        {0.10, 0.05},
        {0.30, 0.10},
        {0.66, 0.30},
        {0.75, 0.70},
        {0.90, 0.80},
        {1.00, 1.00}
    };
    const int K = (int)(sizeof(A) / sizeof(A[0]));
    if (x <= A[0].x) return A[0].y;
    if (x >= A[K-1].x) return A[K-1].y;
    // find segment
    int lo = 0, hi = K - 1;
    while (lo + 1 < hi) {
        int mid = (lo + hi) >> 1;
        if (A[mid].x <= x) lo = mid;
        else hi = mid;
    }
    double t = (x - A[lo].x) / (A[hi].x - A[lo].x);
    return A[lo].y * (1.0 - t) + A[hi].y * t;
}

int main(int argc, char** argv) {
    registerTestlibCmd(argc, argv);

    // Read input
    int N = inf.readInt(2, 200000, "N");
    vector<long long> x(N), y(N);
    for (int i = 0; i < N; i++) {
        x[i] = inf.readLong(-1000000000LL, 1000000000LL, "x[i]");
        y[i] = inf.readLong(-1000000000LL, 1000000000LL, "y[i]");
    }
    // Note: The guarantee that input is sorted by x is provided by the data generator; no validation here to avoid inconsistency with official data.

    // Precompute primes up to N-1 (by city ID)
    vector<char> isPrime(max(2, N), true);
    isPrime[0] = false;
    if (N > 1) isPrime[1] = false;
    for (int i = 2; 1LL * i * i < N; i++) {
        if (isPrime[i]) {
            for (int j = i * i; j < N; j += i) isPrime[j] = false;
        }
    }

    // Read contestant output
    int K = ouf.readInt(N + 1, N + 1, "K");
    vector<int> P(K);
    for (int i = 0; i < K; i++) {
        P[i] = ouf.readInt(0, N - 1, "P[i]");
    }

    // Validate route
    auto invalid = [&](const string& msg) {
        quitp(0.0, ("Invalid output: " + msg).c_str());
    };
    if (P.front() != 0) invalid("Route must start at city 0.");
    if (P.back() != 0) invalid("Route must end at city 0.");

    vector<int> cnt(N, 0);
    for (int i = 1; i < K - 1; i++) cnt[P[i]]++;
    if (cnt[0] != 0) invalid("City 0 must appear only at the endpoints.");
    for (int c = 1; c < N; c++) {
        if (cnt[c] != 1) {
            if (cnt[c] == 0) invalid("City " + to_string(c) + " is missing.");
            else invalid("City " + to_string(c) + " appears more than once.");
        }
    }

    // Compute penalized length L(P)
    auto computeCost = [&](const vector<int>& route) -> double {
        double total = 0.0;
        for (int t = 1; t <= N; t++) {
            int a = route[t - 1];
            int b = route[t];
            double m = 1.0;
            if (t % 10 == 0 && !isPrime[a]) m = 1.1;
            total += m * dist2D(x[a], y[a], x[b], y[b]);
        }
        return total;
    };

    double L_you = computeCost(P);

    // Compute baseline cost L_base for route [0,1,2,...,N-1,0]
    // Input is sorted by x -> baseline is equivalent to monotonic traversal (then return to 0)
    double L_base = 0.0;
    for (int t = 1; t <= N; t++) {
        int a, b;
        if (t < N) {
            a = t - 1;
            b = t;
        } else {
            a = N - 1;
            b = 0;
        }
        double m = 1.0;
        if (t % 10 == 0 && !isPrime[a]) m = 1.1;
        L_base += m * dist2D(x[a], y[a], x[b], y[b]);
    }

    // Degenerate baseline: if L_base == 0, only zero-cost path can get full score
    if (L_base <= 0.0) {
        double eps = 1e-12;
        if (L_you <= L_base + eps) {
            quitp(1.0, "Ratio: 1.0000 (degenerate baseline). RatioUnbounded: 1.0000");
        } else {
            quitp(0.0, "Ratio: 0.0000 (degenerate baseline). RatioUnbounded: 0.0000");
        }
    }

    // Compute r and s
    double r = max(0.0, (L_base - L_you) / L_base); // improvement ratio
    double s = (L_you > 0.0) ? (L_base / L_you) : 1e300;

    // Base scoring: tighter front, widened tail
    const double W1 = 0.20, W2 = 0.80;
    const double r1 = 0.25; // up to 25% improvement contributes linearly
    const double s_start = 1.0 / (1.0 - r1); // = 4/3
    const double tau = 1.25; // convexify tail to widen differences among strong solutions

    // part1: linear up to r1
    double part1_raw = r1 > 0 ? (r / r1) : 0.0;
    double part1 = W1 * clamp01(part1_raw);
    double part1_unbounded = W1 * max(0.0, part1_raw);

    // part2: logarithmic tail, widened span
    double part2 = 0.0;
    double part2_unbounded = 0.0;
    double s_full = pow((double)N, 0.6); // larger than sqrt(N) to make full score harder

    if (s_full > s_start + 1e-12) {
        double num = log(max(s, 1.0)) - log(s_start);
        double den = log(s_full) - log(s_start);
        double frac_raw = (den > 0) ? (num / den) : 0.0;
        double frac = clamp01(frac_raw);
        part2 = W2 * pow(max(frac, 0.0), tau);
        part2_unbounded = W2 * pow(max(frac_raw, 0.0), tau);
    } else if (s_full > 1.0 + 1e-12) {
        double num = log(max(s, 1.0));
        double den = log(s_full);
        double frac_raw = (den > 0) ? (num / den) : 0.0;
        double frac = clamp01(frac_raw);
        part2 = W2 * pow(max(frac, 0.0), tau);
        part2_unbounded = W2 * pow(max(frac_raw, 0.0), tau);
    } else {
        part2 = 0.0;
        part2_unbounded = 0.0;
    }

    double ratio_base_unbounded = part1_unbounded + part2_unbounded;
    double ratio_base = min(1.0, max(0.0, part1 + part2));

    // Visibility remap: widen mid-range (40–60 -> 30–95 approx.)
    double ratio = remapVisibility(ratio_base);
    // double ratio = ratio_base;

    quitp(ratio, "Ratio: %.4f (base=%.4f). RatioUnbounded: %.4f", ratio, ratio_base, ratio_base_unbounded);
    return 0;
}

// Usage and tuning suggestions:
// - If the actual score distribution differs from expectations, adjust anchors in remapVisibility:
//   - To shift a score range up or down, modify the y values at segment endpoints;
//   - To widen the gap between certain scores, adjust the corresponding anchor points.
// - To disable remapping, replace the remapVisibility call with ratio=ratio_base.

// Risk notes and multi-faceted balance:
// - Top segment (0.52→1.00) has smaller slope to avoid "premature ceiling"; strong solutions still need significant s or r improvement to approach full score.
// - Lower score range is slightly compressed to reduce "easy points" feel.
// - Monotonic remapping only changes "visualization scale", not ranking stability; for structural changes to ranking sensitivity, adjust base curve parameters (W1, r1, tau, s_full).
