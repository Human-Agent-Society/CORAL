#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct Vec2 {
    double x, y;
    inline double dot(const Vec2& o) const { return x * o.x + y * o.y; }
};

struct Square {
    // Unit square: side=1
    // Center (cx, cy), edge unit vectors u, v (orthonormal)
    double cx, cy;
    Vec2 u, v; // u = (cosθ, sinθ), v = (-sinθ, cosθ)
    // AABB
    double minX, maxX, minY, maxY;
};

static inline bool isFinite(double x) { return std::isfinite(x); }
static inline double deg2rad(double d) { return d * M_PI / 180.0; }

// Projection of unit square on unit axis a: [centerProj - r, centerProj + r]
// where r = 0.5*(|a·u| + |a·v|)
static inline void projectInterval(const Square& sq, const Vec2& a, double& lo, double& hi) {
    double centerProj = sq.cx * a.x + sq.cy * a.y;
    double r = 0.5 * (fabs(a.dot(sq.u)) + fabs(a.dot(sq.v)));
    lo = centerProj - r;
    hi = centerProj + r;
}

// Positive-area overlap test between two unit squares using SAT with tolerance.
// If on any separating axis the interval overlap <= eps, we consider them non-overlapping (or just touching).
static inline bool squaresHavePositiveAreaOverlap(const Square& A, const Square& B, double eps) {
    const Vec2 axes[4] = { A.u, A.v, B.u, B.v };
    for (int k = 0; k < 4; ++k) {
        double a0, a1, b0, b1;
        projectInterval(A, axes[k], a0, a1);
        projectInterval(B, axes[k], b0, b1);
        double overlap = min(a1, b1) - max(a0, b0);
        if (overlap <= eps) return false; // separated or only touching (within tolerance)
    }
    return true; // strictly overlapping (positive area) on all axes beyond eps
}

// Pack two 32-bit ints (possibly negative) into one 64-bit key for hash map
static inline uint64_t packCellKey(int gx, int gy) {
    uint64_t ux = (uint64_t)(uint32_t)gx;
    uint64_t uy = (uint64_t)(uint32_t)gy;
    return (ux << 32) ^ uy;
}

int main(int argc, char** argv) {
    registerTestlibCmd(argc, argv);

    // Input: single integer n (1 ≤ n ≤ 100000)
    int n = inf.readInt();
    if (n < 1 || n > 100000) {
        quitf(_fail, "n out of allowed range [1, 100000], got %d", n);
    }

    // Constants from statement
    const double epsGeom = 1e-7; // geometry tolerance (containment and non-overlap)
    const double angMin = 0.0, angMax = 180.0;
    const double angTol = 1e-12; // tiny numeric tolerance when checking angle bounds

    // Read reference s(n) from answer file (ans.input)
    double sRef = ans.readDouble();
    if (!isFinite(sRef)) {
        quitf(_fail, "Bad answer file: s(n) is not a finite number.");
    }

    // Read contestant output
    double L = ouf.readDouble();
    if (!isFinite(L)) {
        quitp(0.0, "Invalid output: L is not a finite number.");
    }

    vector<Square> sq(n);
    bool valid = true;
    string reason;
    int bad_i = -1, bad_j = -1;

    // Read squares
    for (int i = 0; i < n; ++i) {
        double cx = ouf.readDouble();
        double cy = ouf.readDouble();
        double a_deg = ouf.readDouble();

        if (!isFinite(cx) || !isFinite(cy) || !isFinite(a_deg)) {
            valid = false;
            reason = "Non-finite number in square parameters.";
            bad_i = i;
            break;
        }
        if (a_deg < angMin - angTol || a_deg >= angMax + angTol) {
            valid = false;
            reason = "Angle out of range [0, 180).";
            bad_i = i;
            break;
        }

        // Clamp angle into [0, 180) robustly (within numerical fuzz)
        if (a_deg < 0) a_deg = 0;
        if (a_deg >= 180) a_deg = nextafter(180.0, 0.0); // just below 180

        double th = deg2rad(a_deg);
        double c = cos(th), s = sin(th);

        sq[i].cx = cx; sq[i].cy = cy;
        sq[i].u = { c, s };
        sq[i].v = { -s, c };

        // Compute AABB using exact extremes for rotated unit square
        double ax = fabs(sq[i].u.x), bx = fabs(sq[i].v.x);
        double ay = fabs(sq[i].u.y), by = fabs(sq[i].v.y);
        double half_wx = 0.5 * (ax + bx);
        double half_wy = 0.5 * (ay + by);
        sq[i].minX = cx - half_wx;
        sq[i].maxX = cx + half_wx;
        sq[i].minY = cy - half_wy;
        sq[i].maxY = cy + half_wy;
    }

    // No extra tokens allowed (beyond whitespace)
    if (!valid) {
        quitp(0.0, ("Invalid output: " + reason + " (at square index " + to_string(bad_i) + ")").c_str());
    }

    // Containment check: AABB must lie within [0, L]^2 with tolerance epsGeom (allow up to eps outside)
    for (int i = 0; i < n; ++i) {
        double over = 0.0;
        over = max(over, -sq[i].minX);
        over = max(over, sq[i].maxX - L);
        over = max(over, -sq[i].minY);
        over = max(over, sq[i].maxY - L);
        if (over > epsGeom) {
            quitp(0.0, "Invalid: containment violated at square %d (excess %.3e > 1e-7).", i + 1, over);
        }
    }

    // Non-overlap check: no positive-area intersection between any two squares
    // Broad-phase: uniform grid hashing on AABBs (cell size = 1.0)
    const double cellSize = 1.0;
    unordered_map<uint64_t, vector<int>> grid;
    grid.reserve((size_t) (n * 2));

    for (int i = 0; i < n; ++i) {
        int gx0 = (int)floor(sq[i].minX / cellSize);
        int gy0 = (int)floor(sq[i].minY / cellSize);
        int gx1 = (int)floor(sq[i].maxX / cellSize);
        int gy1 = (int)floor(sq[i].maxY / cellSize);

        // For each cell the AABB touches, compare with previously inserted squares
        for (int gx = gx0; gx <= gx1; ++gx) {
            for (int gy = gy0; gy <= gy1; ++gy) {
                uint64_t key = packCellKey(gx, gy);
                auto it = grid.find(key);
                if (it != grid.end()) {
                    const vector<int>& vec = it->second;
                    for (int j : vec) {
                        // Optional: quick AABB check before SAT
                        if (sq[i].minX > sq[j].maxX + epsGeom) continue;
                        if (sq[i].maxX < sq[j].minX - epsGeom) continue;
                        if (sq[i].minY > sq[j].maxY + epsGeom) continue;
                        if (sq[i].maxY < sq[j].minY - epsGeom) continue;

                        if (squaresHavePositiveAreaOverlap(sq[i], sq[j], epsGeom)) {
                            quitp(0.0, "Invalid: squares %d and %d overlap (positive area).", j + 1, i + 1);
                        }
                    }
                }
            }
        }
        // Insert current square i into its cells
        for (int gx = gx0; gx <= gx1; ++gx) {
            for (int gy = gy0; gy <= gy1; ++gy) {
                uint64_t key = packCellKey(gx, gy);
                grid[key].push_back(i);
            }
        }
    }

    // Passed validity checks. Compute score per new statement with s(n).
    const double LB = sqrt((double)n);
    const double L0 = ceil(LB);

    // Validate sRef against [LB, L0] to avoid ill-defined bands
    if (!isFinite(sRef)) {
        quitf(_fail, "Bad answer file: s(n) is not finite.");
    }
    // Strictly speaking, statement requires LB ≤ s ≤ L0. Treat violation as problem config error.
    // if (sRef < LB - 1e-9 || sRef > L0 + 1e-9) {
    //     quitf(_fail, "Bad answer file: s(n)=%.12f outside [LB=%.12f, L0=%.12f].", sRef, LB, L0);
    // }
    // Clamp tiny numeric drift
    double s = min(max(sRef, LB), L0);

    const double epsScore = 1e-12;
    double score100 = 0.0;
    const char* band = "baseline-or-worse";

    // Degenerate case: perfect square n (LB == L0)
    if (fabs(L0 - LB) <= 1e-15) {
        // Only two sensible outcomes: exactly LB (==L0) -> 100; else (>= L0) -> 0.
        if (L <= LB + 1e-12) {
            score100 = 100.0;
            band = "degenerate:LB==L0";
        } else {
            score100 = 0.0;
            band = "degenerate:LB==L0";
        }
    } else {
        if (L > L0 + epsScore) {
            score100 = 0;
            band = ">L0";
        } else if (fabs(L - L0) <= epsScore){
            score100 = 1;
            band = "=L0";
        } else if (L <= LB + epsScore) {
            score100 = 100.0;
            band = "LB-band";
        } else if (L <= s + epsScore) {
            // Lower band: LB < L ≤ s
            double denom = s - LB;
            // denom > 0 ensured by earlier checks unless s==LB (nearly)
            if (denom <= 1e-15) {
                // s == LB numerically -> you reached/are above s; only give 100 if L <= LB
                score100 = 100.0 * (L <= LB + 1e-12);
            } else {
                double p2 = (s - L) / denom; // in (0, 1]
                if (p2 < 0.0) p2 = 0.0;
                if (p2 > 1.0) p2 = 1.0;
                double amp = min(1.0, 1.1 * p2);
                score100 = 95.0 + 5.0 * amp;
            }
            band = "lower(LB..s]";
        } else {
            // Upper band: s < L < L0
            double denom = L0 - s;
            if (denom <= 1e-15) {
                // s == L0 numerically -> being strictly < L0 should already imply meeting s, give 95
                score100 = 95.0;
            } else {
                double p1 = (L0 - L) / denom; // in (0, 1)
                if (p1 < 0.0) p1 = 0.0;
                if (p1 > 1.0) p1 = 1.0;
                double amp = min(1.0, 1.1 * p1);
                score100 = 94.0 * amp + 1;
            }
            band = "upper(s..L0)";
        }
    }

    // Ensure [0, 100]
    if (score100 < 0.0) score100 = 0.0;
    double unbounded_ratio = std::max(0.0, score100 / 100.0);
    if (score100 > 100.0) score100 = 100.0;

    // quitp expects a value in [0, 1]. Platforms typically scale by 100.
    double Ratio = score100 / 100.0;
    quitp(Ratio, "Ratio: %.4f, RatioUnbounded: %.4f", Ratio, unbounded_ratio);
    return 0;
}
