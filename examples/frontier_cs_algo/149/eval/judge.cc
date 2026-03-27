#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int N = 30;
static const int Q = 1000;

struct Input {
    int h[N][N - 1];
    int v[N - 1][N];
    int si[Q], sj[Q], ti[Q], tj[Q];
    int a[Q];
    double e[Q];
};

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    Input in;

    // Read map edges
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N - 1; j++) {
            in.h[i][j] = inf.readInt();
        }
    }
    for (int i = 0; i < N - 1; i++) {
        for (int j = 0; j < N; j++) {
            in.v[i][j] = inf.readInt();
        }
    }

    // Read queries and precomputed a_k and noise e_k
    for (int k = 0; k < Q; k++) {
        in.si[k] = inf.readInt();
        in.sj[k] = inf.readInt();
        in.ti[k] = inf.readInt();
        in.tj[k] = inf.readInt();
        in.a[k]  = inf.readInt();
        in.e[k]  = inf.readDouble();
    }

    auto trim_str = [](const string &s) -> string {
        size_t l = 0, r = s.size();
        while (l < r && isspace((unsigned char)s[l])) l++;
        while (r > l && isspace((unsigned char)s[r - 1])) r--;
        return s.substr(l, r - l);
    };

    auto compute_path_length = [&](int k, const string &path, vector<vector<int>> &visited) -> long long {
        int pi = in.si[k], pj = in.sj[k];
        long long sum = 0;

        for (char c : path) {
            if (visited[pi][pj] == k)
                quitf(_wa, "visiting (%d,%d) twice (query %d)", pi, pj, k + 1);
            visited[pi][pj] = k;

            if (c == 'U') {
                if (pi == 0) quitf(_wa, "going outside the map (query %d)", k + 1);
                pi -= 1;
                sum += in.v[pi][pj];
            } else if (c == 'L') {
                if (pj == 0) quitf(_wa, "going outside the map (query %d)", k + 1);
                pj -= 1;
                sum += in.h[pi][pj];
            } else if (c == 'D') {
                if (pi == N - 1) quitf(_wa, "going outside the map (query %d)", k + 1);
                sum += in.v[pi][pj];
                pi += 1;
            } else if (c == 'R') {
                if (pj == N - 1) quitf(_wa, "going outside the map (query %d)", k + 1);
                sum += in.h[pi][pj];
                pj += 1;
            } else {
                quitf(_wa, "unexpected char: '%c' (query %d)", c, k + 1);
            }
        }
        if (!(pi == in.ti[k] && pj == in.tj[k])) {
            quitf(_wa, "not an s-t path (query %d)", k + 1);
        }
        return sum;
    };

    vector<vector<int>> visited(N, vector<int>(N, -1));
    vector<long long> b(Q, 0);

    double score_sum = 0.0;

    for (int k = 0; k < Q; k++) {
        // Send s_k and t_k to contestant
        cout << in.si[k] << " " << in.sj[k] << " " << in.ti[k] << " " << in.tj[k] << endl;

        // Read non-empty line with the path
        string path;
        do {
            path = ouf.readLine();
            path = trim_str(path);
        } while (path.empty());

        long long bk = compute_path_length(k, path, visited);
        if (in.a[k] > bk) {
            quitf(_fail, "internal error: a_k (%d) > b_k (%lld) at query %d", in.a[k], bk, k + 1);
        }
        b[k] = bk;

        // Respond with noisy length
        long long feedback = llround((long double)bk * in.e[k]);
        cout << feedback << endl;

        // Update scores
        score_sum = score_sum * 0.998 + (double)in.a[k] / (double)bk;
    }

    long long score = llround(2312311.0 * score_sum);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
    return 0;
}