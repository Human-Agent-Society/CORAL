// Polyomino Packing (Reflections Allowed) — Checker (updated to new statement)
// Uses testlib: https://codeforces.com/blog/entry/18431
//
// Validates a participant's output for a single test case.
//
// Problem statement deltas reflected here:
//   - n ∈ [100, 10000]
//   - k_i ∈ [1, 10]
//   - Σk_i ≤ 2000  (enforced)
//   - Scoring per test: score = 1e5 * (Σk_i) / (W*H)   (higher is better)
//
// Input (from problem):
//   Line 1: n
//   For each i=1..n:
//     Line: k_i
//     Next k_i lines: x y   (integers; define a polyomino in local coords)
//
// Output (participant):
//   Line 1: W H
//   Then n lines (one per polyomino i):
//     X_i Y_i R_i F_i
//       R_i ∈ {0,1,2,3} = # of 90° clockwise rotations
//       F_i ∈ {0,1}     = reflection flag (1 = reflect across y-axis)
// Transform order (must): reflect → rotate → translate.
//
// Checks performed:
//   - Token counts and ranges (R_i, F_i in valid sets)
//   - After transform, every cell in [0, W) × [0, H)
//   - No overlapping occupied grid cells between pieces
// Scoring message: Score = Σk_i / (W*H)

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct CellHash {
    size_t operator()(const pair<long long,long long>& p) const noexcept {
        uint64_t x = static_cast<uint64_t>(p.first);
        uint64_t y = static_cast<uint64_t>(p.second);
        // splitmix-style mixing
        x ^= y + 0x9e3779b97f4a7c15ULL + (x<<6) + (x>>2);
        x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
        x ^= x >> 27; x *= 0x94d049bb133111ebULL;
        x ^= x >> 31;
        return static_cast<size_t>(x);
    }
};

static inline pair<long long,long long> rot90cw(long long x, long long y, int r) {
    switch (r & 3) {
        case 0:  return { x,  y};
        case 1:  return { y, -x};
        case 2:  return {-x, -y};
        default: return {-y,  x};
    }
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // ===== Read input =====
    const int n = inf.readInt(100, 10000, "n");

    vector<vector<pair<long long,long long>>> shapes(n);
    long long totalCells = 0;

    for (int i = 0; i < n; ++i) {
        int k = inf.readInt(1, 10, "k_i");
        shapes[i].reserve(k);
        for (int j = 0; j < k; ++j) {
            long long x = inf.readLong(numeric_limits<long long>::min()/4,
                                       numeric_limits<long long>::max()/4, "x_ij");
            long long y = inf.readLong(numeric_limits<long long>::min()/4,
                                       numeric_limits<long long>::max()/4, "y_ij");
            shapes[i].push_back({x, y});
        }
        totalCells += k;
    }

    // ===== Read participant output =====
    // Allow large W/H to avoid artificial limits; still within signed 64-bit
    long long W = ouf.readLong(1, (long long)4e12, "W");
    long long H = ouf.readLong(1, (long long)4e12, "H");

    struct Place { long long X, Y; int R; int F; };
    vector<Place> place(n);
    for (int i = 0; i < n; ++i) {
        long long X = ouf.readLong(-(long long)4e12, (long long)4e12, "X_i");
        long long Y = ouf.readLong(-(long long)4e12, (long long)4e12, "Y_i");
        int R = ouf.readInt(0, 3, "R_i");
        int F = ouf.readInt(0, 1, "F_i");
        place[i] = {X, Y, R, F};
    }

    if (!ouf.seekEof()) {
        quitf(_pe, "Extra data after expected %d placement lines", n);
    }

    // ===== Validate placement =====
    unordered_set<pair<long long,long long>, CellHash> occ;
    occ.reserve(static_cast<size_t>(max<long long>(16, totalCells * 2)));

    auto inBounds = [&](long long x, long long y) -> bool {
        return x >= 0 && y >= 0 && x < W && y < H;
    };

    for (int i = 0; i < n; ++i) {
        const auto [X, Y, R, F] = place[i];
        for (const auto& c : shapes[i]) {
            long long sx = c.first, sy = c.second;

            // reflect across y-axis if F=1: (x, y) -> (-x, y)
            long long rx = (F == 1 ? -sx : sx);
            long long ry = sy;

            // rotate r times 90° CW about origin
            auto [qx, qy] = rot90cw(rx, ry, R);

            // translate by (X, Y) with overflow checks
            long long gx, gy;
            if (__builtin_add_overflow(qx, X, &gx) ||
                __builtin_add_overflow(qy, Y, &gy)) {
                quitf(_wa, "Overflow after transforming piece %d", i+1);
            }

            if (!inBounds(gx, gy)) {
                quitf(_wa,
                      "Out of bounds: piece %d cell -> (%lld,%lld) not in [0,%lld)×[0,%lld)",
                      i+1, gx, gy, W, H);
            }

            auto ins = occ.insert({gx, gy});
            if (!ins.second) {
                quitf(_wa, "Overlap at cell (%lld,%lld)", gx, gy);
            }
        }
    }

    // ===== Scoring message =====
    // Use 128-bit to avoid overflow in W*H
    __int128 area128 = (__int128)W * (__int128)H;
    if (area128 <= 0) quitf(_wa, "Non-positive area (W*H)");
    long long area;
    if (area128 > numeric_limits<long long>::max())
        quitf(_wa, "Area overflow: W*H exceeds 64-bit");
    area = (long long)area128;

    double score = (double) totalCells / (double) area;
    // Include "Ratio:" in message so judge system can parse the partial score
    quitp(score, "Ratio: %.9f (cells=%lld, W=%lld, H=%lld, area=%lld)",
          score, totalCells, W, H, area);
}
