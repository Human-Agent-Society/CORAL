#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    const int N = 20;
    const int L = 200;

    // Read input
    long long si = inf.readInt();
    long long sj = inf.readInt();
    long long ti = inf.readInt();
    long long tj = inf.readInt();
    double p = inf.readDouble();

    vector<vector<bool>> hs(N, vector<bool>(N - 1, false)); // true if wall between (i,j)-(i,j+1)
    vector<vector<bool>> vs(N - 1, vector<bool>(N, false)); // true if wall between (i,j)-(i+1,j)

    for (int i = 0; i < N; i++) {
        string line = inf.readToken();
        if ((int)line.size() != N - 1) quitf(_fail, "invalid hs line length");
        for (int j = 0; j < N - 1; j++) {
            if (line[j] != '0' && line[j] != '1') quitf(_fail, "invalid hs character");
            hs[i][j] = (line[j] == '1');
        }
    }
    for (int i = 0; i < N - 1; i++) {
        string line = inf.readToken();
        if ((int)line.size() != N) quitf(_fail, "invalid vs line length");
        for (int j = 0; j < N; j++) {
            if (line[j] != '0' && line[j] != '1') quitf(_fail, "invalid vs character");
            vs[i][j] = (line[j] == '1');
        }
    }

    // Read output (route string). Allow empty after trimming.
    auto trimBoth = [](const string& s) -> string {
        size_t l = 0, r = s.size();
        while (l < r && isspace((unsigned char)s[l])) l++;
        while (r > l && isspace((unsigned char)s[r - 1])) r--;
        return s.substr(l, r - l);
    };
    string outRaw = ouf.readString();
    string out = trimBoth(outRaw);

    if ((int)out.size() > L) {
        quitf(_wa, "too long output");
    }

    auto can_move = [&](int i, int j, int d) -> bool {
        // 0: U, 1: L, 2: D, 3: R
        if (d == 0) return i > 0 && !vs[i - 1][j];
        if (d == 1) return j > 0 && !hs[i][j - 1];
        if (d == 2) return i < N - 1 && !vs[i][j];
        if (d == 3) return j < N - 1 && !hs[i][j];
        return false;
    };

    // Prepare probability grid
    vector<vector<double>> crt(N, vector<double>(N, 0.0));
    crt[(int)si][(int)sj] = 1.0;

    double sum = 0.0;
    double goalAccum = 0.0;

    for (int t = 0; t < (int)out.size(); t++) {
        char c = out[t];
        int d = -1;
        if (c == 'U') d = 0;
        else if (c == 'L') d = 1;
        else if (c == 'D') d = 2;
        else if (c == 'R') d = 3;
        else {
            quitf(_wa, "illegal char: %c", c);
        }

        vector<vector<double>> nxt(N, vector<double>(N, 0.0));
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
                double prob = crt[i][j];
                if (prob == 0.0) continue;
                if (can_move(i, j, d)) {
                    int i2 = i, j2 = j;
                    if (d == 0) i2 = i - 1;
                    else if (d == 1) j2 = j - 1;
                    else if (d == 2) i2 = i + 1;
                    else if (d == 3) j2 = j + 1;
                    nxt[i2][j2] += prob * (1.0 - p);
                    nxt[i][j] += prob * p;
                } else {
                    nxt[i][j] += prob;
                }
            }
        }

        crt.swap(nxt);

        double atGoal = crt[(int)ti][(int)tj];
        sum += atGoal * (2.0 * L - t);
        goalAccum += atGoal;
        crt[(int)ti][(int)tj] = 0.0;
    }

    // Final score calculation
    long long score_val = llround(1e8 * sum / (2.0 * L));

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score_val - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score_val - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score_val, score_ratio, unbounded_ratio);
}