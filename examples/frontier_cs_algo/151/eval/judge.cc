#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct InputData {
    int N;
    int si, sj;
    vector<string> c;
};

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read input
    InputData in;
    in.N = inf.readInt();
    in.si = inf.readInt();
    in.sj = inf.readInt();
    in.c.resize(in.N);
    for (int i = 0; i < in.N; i++) {
        in.c[i] = inf.readToken();
        if ((int)in.c[i].size() != in.N) {
            quitf(_wa, "Invalid input line length");
        }
    }

    // Read output: allow empty output, but not more than one token
    string out;
    if (ouf.seekEof()) {
        out = "";
    } else {
        out = ouf.readToken();
        if (!ouf.seekEof()) {
            quitf(_wa, "Too Many Output");
        }
    }

    // Simulate route
    int pi = in.si, pj = in.sj;
    long long length = 0;
    vector<pair<int,int>> ps;
    ps.emplace_back(pi, pj);

    for (char c : out) {
        int di = 0, dj = 0;
        if (c == 'U') { di = -1; dj = 0; }
        else if (c == 'D') { di = 1; dj = 0; }
        else if (c == 'L') { di = 0; dj = -1; }
        else if (c == 'R') { di = 0; dj = 1; }
        else {
            // Illegal character
            string msg = "Illegal output: ";
            msg.push_back(c);
            quitf(_wa, "%s", msg.c_str());
        }
        pi += di;
        pj += dj;
        if (pi < 0 || pi >= in.N || pj < 0 || pj >= in.N || in.c[pi][pj] == '#') {
            quitf(_wa, "Visiting an obstacle");
        }
        length += (in.c[pi][pj] - '0');
        ps.emplace_back(pi, pj);
    }

    // Compute visibility
    vector<vector<bool>> vis(in.N, vector<bool>(in.N, false));
    auto markVisibilityFrom = [&](int ci, int cj) {
        // Up
        for (int i = ci; i >= 0; --i) {
            if (in.c[i][cj] == '#') break;
            vis[i][cj] = true;
        }
        // Down
        for (int i = ci; i < in.N; ++i) {
            if (in.c[i][cj] == '#') break;
            vis[i][cj] = true;
        }
        // Left
        for (int j = cj; j >= 0; --j) {
            if (in.c[ci][j] == '#') break;
            vis[ci][j] = true;
        }
        // Right
        for (int j = cj; j < in.N; ++j) {
            if (in.c[ci][j] == '#') break;
            vis[ci][j] = true;
        }
    };
    for (auto &p : ps) markVisibilityFrom(p.first, p.second);

    // Check return to start
    if (ps.back().first != in.si || ps.back().second != in.sj) {
        quitf(_wa, "You have to go back to the starting point");
    }

    // Compute score
    long long num = 0, den = 0;
    for (int i = 0; i < in.N; i++) {
        for (int j = 0; j < in.N; j++) {
            if (in.c[i][j] != '#') {
                den++;
                if (vis[i][j]) num++;
            }
        }
    }

    double score = 1e4 * (double)num / (double)den;
    if (num == den) {
        // length should be > 0 if full coverage is achieved
        if (length <= 0) {
            quitf(_wa, "Invalid length for full coverage");
        }
        score += 1e7 * (double)in.N / (double)length;
    }
    long long finalScore = llround(score);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(finalScore - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(finalScore - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", finalScore, score_ratio, unbounded_ratio);
}