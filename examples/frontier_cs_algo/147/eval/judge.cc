#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const long long W = 10000;

struct Rect {
    long long x1, y1, x2, y2;
    long long size() const { return (x2 - x1) * (y2 - y1); }
};

static inline bool intersect(const Rect& r1, const Rect& r2) {
    return min(r1.x2, r2.x2) > max(r1.x1, r2.x1) && min(r1.y2, r2.y2) > max(r1.y1, r2.y1);
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    int n = inf.readInt();
    vector<long long> xs(n), ys(n), rs(n);
    for (int i = 0; i < n; i++) {
        xs[i] = inf.readLong();
        ys[i] = inf.readLong();
        rs[i] = inf.readLong();
    }

    vector<Rect> out(n);
    for (int i = 0; i < n; i++) {
        out[i].x1 = ouf.readLong();
        out[i].y1 = ouf.readLong();
        out[i].x2 = ouf.readLong();
        out[i].y2 = ouf.readLong();
    }
    if (!ouf.seekEof()) {
        quitf(_wa, "Too many rectangles");
    }

    double score = 0.0;
    for (int i = 0; i < n; i++) {
        const Rect& r = out[i];
        if (r.x1 < 0 || r.x2 > W || r.y1 < 0 || r.y2 > W) {
            quitf(_wa, "rectangle %d is out of range", i);
        }
        if (r.x1 >= r.x2 || r.y1 >= r.y2) {
            quitf(_wa, "rectangle %d does not have positive area", i);
        }
        // Check if contains (xi, yi) according to Rust logic (xi in [x1, x2), yi in [y1, y2))
        if (!(r.x1 <= xs[i] && xs[i] < r.x2 && r.y1 <= ys[i] && ys[i] < r.y2)) {
            continue;
        }
        for (int j = 0; j < i; j++) {
            if (intersect(out[i], out[j])) {
                quitf(_wa, "rectangles %d and %d overlap", j, i);
            }
        }
        long long si = r.size();
        long long ri = rs[i];
        double s = (double)min(si, ri) / (double)max(si, ri);
        score += 1.0 - (1.0 - s) * (1.0 - s);
    }
    score /= n;
    score *= 1e9;
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();
    long long final_score = llround(score);

    double score_ratio = max(0.0, min(1.0, (double)(final_score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(final_score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", final_score, score_ratio, unbounded_ratio);
}