#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int N = 1000;
static const int M = 50;

static inline long long manhattan(pair<int,int> a, pair<int,int> b) {
    return llabs((long long)a.first - b.first) + llabs((long long)a.second - b.second);
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    vector<pair<int,int>> from(N), to(N);
    // Read input
    for (int i = 0; i < N; i++) {
        int a = inf.readInt(0, 800);
        int b = inf.readInt(0, 800);
        int c = inf.readInt(0, 800);
        int d = inf.readInt(0, 800);
        from[i] = {a, b};
        to[i] = {c, d};
    }

    // Parse output blocks; only the last block is used for scoring
    bool anyOutput = false;
    vector<int> r_last;
    vector<pair<int,int>> path_last;

    while (!ouf.seekEof()) {
        int m = ouf.readInt(0, 1000);
        vector<int> r(m);
        for (int i = 0; i < m; i++) {
            int idx = ouf.readInt(1, N);
            r[i] = idx - 1; // convert to 0-based
        }
        long long n = ouf.readLong(0LL, 1000000000LL);
        vector<pair<int,int>> path;
        path.reserve((size_t)min<long long>(n, 10000000LL)); // avoid huge reserve
        for (long long i = 0; i < n; i++) {
            int x = ouf.readInt(0, 800);
            int y = ouf.readInt(0, 800);
            path.emplace_back(x, y);
        }
        r_last.swap(r);
        path_last.swap(path);
        anyOutput = true;
    }

    if (!anyOutput) {
        quitf(_wa, "empty output");
    }

    const vector<int>& r = r_last;
    const vector<pair<int,int>>& path = path_last;

    // Compute total time
    long long time = 0;
    for (size_t i = 1; i < path.size(); i++) {
        time += manhattan(path[i - 1], path[i]);
    }

    // Validate r indices uniqueness
    for (int i = 0; i < (int)r.size(); i++) {
        if (r[i] < 0 || r[i] >= N) {
            // In rust parser: "Illegal output (r[i] = value)" with 1-based value
            quitf(_wa, "Illegal output (r[%d] = %d)", i + 1, r[i] + 1);
        }
        for (int j = 0; j < i; j++) {
            if (r[i] == r[j]) {
                quitf(_wa, "Illegal output (r[%d] = r[%d])", i + 1, j + 1);
            }
        }
    }

    // Validate path bounds and endpoints
    for (size_t i = 0; i < path.size(); i++) {
        if (path[i].first < 0 || path[i].first > 800 || path[i].second < 0 || path[i].second > 800) {
            quitf(_wa, "Illegal output");
        }
    }
    if (path.empty() || path.front() != make_pair(400, 400)) {
        quitf(_wa, "Illegal output (x[1],y[1]) != (400, 400)");
    } else if (path.back() != make_pair(400, 400)) {
        quitf(_wa, "Illegal output (x[n],y[n]) != (400, 400)");
    }

    // Build first and last visit maps
    map<pair<int,int>, int> first_visit;
    map<pair<int,int>, int> last_visit;
    for (int i = 0; i < (int)path.size(); i++) {
        if (!first_visit.count(path[i])) first_visit[path[i]] = i;
        last_visit[path[i]] = i;
    }

    // Check all deliveries in r are completed: from visited before to
    for (int k = 0; k < (int)r.size(); k++) {
        int idx = r[k];
        auto fIt = first_visit.find(from[idx]);
        auto lIt = last_visit.find(to[idx]);
        if (fIt != first_visit.end() && lIt != last_visit.end()) {
            if (fIt->second >= lIt->second) {
                quitf(_wa, "%d-th delivery has not been completed", idx + 1);
            }
        } else {
            quitf(_wa, "%d-th delivery has not been completed", idx + 1);
        }
    }

    if ((int)r.size() != M) {
        quitf(_wa, "Illegal output (m != 50)");
    }

    long long score = llround(1e8 / (1000.0 + (double)time));
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}