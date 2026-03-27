#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int N = 30;

static const int ROTATE_[8] = {1, 2, 3, 0, 5, 4, 7, 6};
static const int TO_[8][4] = {
    {1, 0, -1, -1},
    {3, -1, -1, 0},
    {-1, -1, 3, 2},
    {-1, 2, 1, -1},
    {1, 0, 3, 2},
    {3, 2, 1, 0},
    {2, -1, 0, -1},
    {-1, 3, -1, 1},
};
static const int di[4] = {0, -1, 0, 1};
static const int dj[4] = {-1, 0, 1, 0};

static string trim_ws(const string &s) {
    size_t l = 0, r = s.size();
    while (l < r && isspace(static_cast<unsigned char>(s[l]))) ++l;
    while (r > l && isspace(static_cast<unsigned char>(s[r - 1]))) --r;
    return s.substr(l, r - l);
}

long long compute_score(const vector<vector<int>>& inputTiles, const vector<int>& out) {
    vector<vector<int>> tiles = inputTiles;
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            int r = out[i * N + j] % 4;
            int t = tiles[i][j];
            for (int k = 0; k < r; k++) t = ROTATE_[t];
            tiles[i][j] = t;
        }
    }

    vector<vector<array<char,4>>> used(N, vector<array<char,4>>(N, {0,0,0,0}));
    vector<long long> loops;

    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            for (int d = 0; d < 4; d++) {
                if (TO_[tiles[i][j]][d] == -1) continue;
                if (used[i][j][d]) continue;

                int i2 = i, j2 = j, d2 = d;
                long long length = 0;

                while (!used[i2][j2][d2]) {
                    int nextDir = TO_[tiles[i2][j2]][d2];
                    if (nextDir == -1) break;
                    length += 1;
                    used[i2][j2][d2] = 1;
                    used[i2][j2][nextDir] = 1;
                    int ni = i2 + di[nextDir];
                    int nj = j2 + dj[nextDir];
                    if (ni < 0 || ni >= N || nj < 0 || nj >= N) {
                        i2 = ni; j2 = nj; d2 = (nextDir + 2) % 4; // out of bounds marker state
                        break;
                    }
                    i2 = ni; j2 = nj; d2 = (nextDir + 2) % 4;
                }

                if (i2 == i && j2 == j && d2 == d) {
                    loops.push_back(length);
                }
            }
        }
    }

    if ((int)loops.size() <= 1) return 0;
    sort(loops.begin(), loops.end());
    long long L1 = loops[(int)loops.size() - 1];
    long long L2 = loops[(int)loops.size() - 2];
    return L1 * L2;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Parse input tiles
    vector<vector<int>> tiles(N, vector<int>(N, 0));
    for (int i = 0; i < N; i++) {
        string s = inf.readToken();
        if ((int)s.size() != N) {
            quitf(_wa, "Illegal input line length at row %d: %d", i, (int)s.size());
        }
        for (int j = 0; j < N; j++) {
            if (s[j] < '0' || s[j] > '7') {
                quitf(_wa, "Illegal tile character at (%d,%d): %c", i, j, s[j]);
            }
            tiles[i][j] = s[j] - '0';
        }
    }

    // Parse output lines (possibly multiple), use the last one
    vector<vector<int>> outs;
    while (!ouf.seekEof()) {
        string line = ouf.readLine();
        string t = trim_ws(line);
        if (t.empty()) continue; // ignore empty trimmed lines
        vector<int> tmp;
        tmp.reserve(N * N);
        for (char c : t) {
            if (c < '0' || c > '3') {
                quitf(_wa, "Illegal output character: %c", c);
            }
            tmp.push_back(c - '0');
        }
        if ((int)tmp.size() != N * N) {
            quitf(_wa, "Illegal output length: %d", (int)t.size());
        }
        outs.push_back(tmp);
    }
    if (outs.empty()) {
        quitf(_wa, "empty output");
    }

    long long score = 0;
    try {
        score = compute_score(tiles, outs.back());
    } catch (...) {
        quitf(_wa, "error");
    }

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}