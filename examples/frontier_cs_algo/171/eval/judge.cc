#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int U = 0, D = 1, L = 2, R = 3;
static const char DIRS[4] = {'U','D','L','R'};
static const long long di[4] = {-1, 1, 0, 0};
static const long long dj[4] = {0, 0, -1, 1};

int dir_index(char c) {
    for (int k = 0; k < 4; k++) if (DIRS[k] == c) return k;
    return -1;
}

long long compute_score() {
    // Read input
    long long N = inf.readLong();
    long long M = inf.readLong();
    vector<pair<long long,long long>> ps(M);
    for (long long k = 0; k < M; k++) {
        long long x = inf.readLong();
        long long y = inf.readLong();
        ps[k] = {x, y};
    }

    // Parse output
    struct Action { char a; int d; };
    vector<Action> out;
    while (!ouf.seekEof()) {
        string as = ouf.readToken();
        if (as.size() != 1) quitf(_wa, "Invalid action: %s", as.c_str());
        char a = as[0];
        if (a != 'M' && a != 'S' && a != 'A') quitf(_wa, "Invalid action: %c", a);

        if (ouf.seekEof()) quitf(_wa, "Unexpected EOF after action");
        string ds = ouf.readToken();
        if (ds.size() != 1) quitf(_wa, "Invalid direction: %s", ds.c_str());
        char dc = ds[0];
        int d = dir_index(dc);
        if (d == -1) quitf(_wa, "Invalid direction: %c", dc);

        out.push_back({a, d});
        if ((long long)out.size() > 2LL * N * M) {
            quitf(_wa, "Too many actions: %lld", (long long)out.size());
        }
    }

    // Simulate
    long long pi = ps[0].first;
    long long pj = ps[0].second;
    long long done = 1;
    vector<vector<char>> block((size_t)N, vector<char>((size_t)N, 0));

    auto in_range = [&](long long x, long long y) -> bool {
        return (0 <= x && x < N && 0 <= y && y < N);
    };

    for (size_t t = 0; t < out.size(); t++) {
        char a = out[t].a;
        int d = out[t].d;
        if (a == 'M') {
            long long ni = pi + di[d];
            long long nj = pj + dj[d];
            if (!in_range(ni, nj)) {
                quitf(_wa, "Out of range (M %c)", DIRS[d]);
            }
            if (block[(size_t)ni][(size_t)nj]) {
                quitf(_wa, "Blocked (M %c)", DIRS[d]);
            }
            pi = ni; pj = nj;
        } else if (a == 'S') {
            while (true) {
                long long ni = pi + di[d];
                long long nj = pj + dj[d];
                if (!in_range(ni, nj)) break;
                if (block[(size_t)ni][(size_t)nj]) break;
                pi = ni; pj = nj;
            }
        } else if (a == 'A') {
            long long ai = pi + di[d];
            long long aj = pj + dj[d];
            if (!in_range(ai, aj)) {
                quitf(_wa, "Out of range (A %c)", DIRS[d]);
            }
            block[(size_t)ai][(size_t)aj] ^= 1;
        }

        if (done < M && ps[(size_t)done].first == pi && ps[(size_t)done].second == pj) {
            done++;
        }
    }

    long long score;
    if (done < M) {
        score = done;
    } else {
        score = M + 2LL * N * M - (long long)out.size();
    }
    return score;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    long long score = compute_score();
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}