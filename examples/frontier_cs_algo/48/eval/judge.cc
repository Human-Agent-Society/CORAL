#include "testlib.h"
#include <cmath>
#include <vector>
#include <array>
#include <limits>
#include <algorithm>
#include <string>

using namespace std;

/*
Sphere Packing in a Cube — custom checker (optimization)

Input (.in): a single integer n (number of equal spheres).
Output (.out): exactly n lines, each with three real numbers x y z (centers), all in [0,1].
Answer (.ans): two doubles — baseline_radius and best_radius — used for normalization.

Scoring per test:
  Let r_geom = min( 0.5 * min_{i!=j} ||ci - cj|| ,  min_i dist_to_faces(ci) )
  score = clamp( (r_geom - baseline) / (best - baseline), 0, 1 )

The checker prints "Ratio: <score>" to enable partial scoring capture.
*/

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read n
    int n = inf.readInt(1, 2000000000, "n"); // logical upper bound; actual tests are modest

    // Read participant output: exactly n triples of doubles
    vector<array<double,3>> c;
    c.reserve(n);
    const double EPS = 1e-12;

    for (int i = 0; i < n; ++i) {
        // If the output ends early (ignoring blanks)
        ouf.skipBlanks();
        if (ouf.eof()) {
            quitf(_wa, "Expected %d points, but output ended early at point %d", n, i+1);
        }

        double x = ouf.readDouble();
        double y = ouf.readDouble();
        double z = ouf.readDouble();

        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
            quitf(_wa, "Non-finite coordinate at point %d", i+1);
        }

        if (x < -EPS || x > 1.0 + EPS || y < -EPS || y > 1.0 + EPS || z < -EPS || z > 1.0 + EPS) {
            quitf(_wa, "Coordinate at point %d is outside [0,1] (x=%.17g, y=%.17g, z=%.17g)", i+1, x, y, z);
        }

        // Clamp slight epsilon overflow into [0,1]
        x = min(1.0, max(0.0, x));
        y = min(1.0, max(0.0, y));
        z = min(1.0, max(0.0, z));
        c.push_back({x,y,z});
    }

    // Ensure there's no extra significant output (allow trailing whitespace)
    ouf.skipBlanks();
    if (!ouf.eof()) {
        string extra = ouf.readToken();
        quitf(_wa, "Extra output detected after %d points: '%s' ...", n, extra.c_str());
    }

    // Read baseline and best from .ans
    double baseline = ans.readDouble();
    double best = ans.readDouble();

    if (!std::isfinite(baseline) || !std::isfinite(best)) {
        quitf(_fail, "Invalid .ans: baseline/best are not finite");
    }

    // Compute distance to faces for each center
    double d_face = numeric_limits<double>::infinity();
    for (int i = 0; i < n; ++i) {
        const auto &p = c[i];
        // min distance to any of the six faces
        double df = std::min(std::min(p[0], 1.0 - p[0]),
                   std::min(std::min(p[1], 1.0 - p[1]),
                            std::min(p[2], 1.0 - p[2])));
        d_face = std::min(d_face, df);
    }
    if (!std::isfinite(d_face)) d_face = 0.0;

    // Compute half of the minimum pairwise distance
    double min_d2 = numeric_limits<double>::infinity();
    for (int i = 0; i < n; ++i) {
        const auto &a = c[i];
        for (int j = i+1; j < n; ++j) {
            const auto &b = c[j];
            double dx = a[0] - b[0];
            double dy = a[1] - b[1];
            double dz = a[2] - b[2];
            double d2 = dx*dx + dy*dy + dz*dz;
            if (d2 < min_d2) min_d2 = d2;
        }
    }

    double r_pair = (min_d2 == numeric_limits<double>::infinity()) ? d_face : 0.5 * sqrt(min_d2);
    double r_geom = std::min(d_face, r_pair);
    if (!std::isfinite(r_geom) || r_geom < 0) r_geom = 0.0;

    // Scoring
    double score = 0.0, unbounded_score = 0.0;
    const double EPS_DEN = 1e-15;
    if (best <= baseline + EPS_DEN) {
        score = (r_geom + 1e-18 >= best) ? 1.0 : 0.0;
    } else {
        score = (r_geom - baseline) / (best - baseline);
        unbounded_score = std::max(0.0, score);
        if (score < 0.0) score = 0.0;
        if (score > 1.0) score = 1.0;
    }

    quitp(score, "Radius: %.12f. Ratio: %.6f, RatioUnbounded: %.6f", r_geom, score, unbounded_score);
}
