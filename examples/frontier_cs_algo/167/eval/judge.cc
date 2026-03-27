#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

using ll = long long;

static const ll D = 100000;

struct Input {
    int N;
    vector<pair<ll, ll>> ps; // size 2N
};

static Input readInput() {
    Input in;
    in.N = inf.readInt();
    in.ps.resize(2 * in.N);
    for (int i = 0; i < 2 * in.N; i++) {
        ll x = inf.readLong(0, D);
        ll y = inf.readLong(0, D);
        in.ps[i] = {x, y};
    }
    return in;
}

static vector<pair<ll, ll>> readLastPolygonFromOutput() {
    vector<pair<ll, ll>> lastPoly;
    while (!ouf.seekEof()) {
        int m = ouf.readInt(4, 1000, "m");
        vector<pair<ll, ll>> poly;
        poly.reserve(m);
        for (int i = 0; i < m; i++) {
            ll a = ouf.readLong(0, D);
            ll b = ouf.readLong(0, D);
            poly.emplace_back(a, b);
        }
        lastPoly.swap(poly);
    }
    return lastPoly;
}

static pair<long long, string> compute_score_details(const Input& input, const vector<pair<ll, ll>>& out) {
    ll len = 0;

    // Basic edge checks: axis-aligned, consecutive duplicate vertex, and collinear direction constraint
    int m = (int)out.size();
    for (int i = 0; i < m; i++) {
        auto p = out[i];
        auto q = out[(i + 1) % m];
        auto r = out[(i + 2) % m];

        if (p == q) {
            return {0, "Two consecutive vertices share the same coordinates."};
        } else if (p.first == q.first) {
            len += llabs(p.second - q.second);
            if (q.first == r.first) {
                ll a = p.second - q.second;
                ll b = r.second - q.second;
                if (a * b > 0) {
                    return {0, "The polygon is self-intersecting."};
                }
            }
        } else if (p.second == q.second) {
            len += llabs(p.first - q.first);
            if (q.second == r.second) {
                ll a = p.first - q.first;
                ll b = r.first - q.first;
                if (a * b > 0) {
                    return {0, "The polygon is self-intersecting."};
                }
            }
        } else {
            // i-th edge not axis-aligned
            char buf[256];
            snprintf(buf, sizeof(buf),
                     "The %d-th edge is not parallel to the axes. ((%lld, %lld) - (%lld, %lld))",
                     i, p.first, p.second, q.first, q.second);
            return {0, string(buf)};
        }
    }

    // Non-adjacent edge intersection check (including touching at endpoints)
    for (int i = 0; i < m; i++) {
        for (int dt = 2; dt < m - 1; dt++) {
            int j = (i + dt) % m;
            auto p1 = out[i];
            auto p2 = out[(i + 1) % m];
            auto q1 = out[j];
            auto q2 = out[(j + 1) % m];

            ll pminx = min(p1.first, p2.first);
            ll pmaxx = max(p1.first, p2.first);
            ll pminy = min(p1.second, p2.second);
            ll pmaxy = max(p1.second, p2.second);

            ll qminx = min(q1.first, q2.first);
            ll qmaxx = max(q1.first, q2.first);
            ll qminy = min(q1.second, q2.second);
            ll qmaxy = max(q1.second, q2.second);

            if (max(pminx, qminx) <= min(pmaxx, qmaxx)) {
                if (max(pminy, qminy) <= min(pmaxy, qmaxy)) {
                    return {0, "The polygon is self-intersecting."};
                }
            }
        }
    }

    if (len > 4 * D) {
        return {0, "The length is too long: " + to_string(len) + "."};
    }

    // Compute score
    long long score = 1;
    for (int i = 0; i < (int)input.ps.size(); i++) {
        auto r = input.ps[i];
        bool inside = false;
        for (int j = 0; j < m; j++) {
            auto p = out[j];
            auto q = out[(j + 1) % m];

            ll x0 = min(p.first, q.first);
            ll x1 = max(p.first, q.first);
            ll y0 = min(p.second, q.second);
            ll y1 = max(p.second, q.second);

            // On-edge is inside
            if (x0 <= r.first && r.first <= x1 && y0 <= r.second && r.second <= y1) {
                inside = true;
                break;
            }

            // Ray casting: horizontal edges strictly above the point, [x0, x1) interval
            if (p.second == q.second && p.second > r.second) {
                if (x0 <= r.first && r.first < x1) {
                    inside = !inside;
                }
            }
        }
        if (inside) {
            if (i < input.N) score += 1;
            else score -= 1;
        }
    }

    if (score < 0) score = 0;
    return {score, ""};
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    Input in = readInput();
    vector<pair<ll, ll>> poly = readLastPolygonFromOutput(); // may be empty

    auto [score, err] = compute_score_details(in, poly);
    if (!err.empty()) {
        quitf(_wa, "%s", err.c_str());
    }
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}