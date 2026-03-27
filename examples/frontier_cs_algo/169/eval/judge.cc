#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct InputData {
    int n;
    vector<string> cs;
};

static InputData parseInput() {
    InputData in;
    in.n = inf.readInt();
    inf.readEoln();
    in.cs.resize(in.n);
    for (int i = 0; i < in.n; i++) {
        in.cs[i] = inf.readToken();
        inf.readEoln();
        ensuref((int)in.cs[i].size() == in.n, "Invalid row length at row %d: expected %d, got %d", i, in.n, (int)in.cs[i].size());
    }
    return in;
}

static vector<pair<char, int>> parseOutput(int n) {
    vector<pair<char, int>> ops;
    while (!ouf.seekEof()) {
        string dstr = ouf.readWord();
        ensuref(!dstr.empty(), "Empty direction token");
        ensuref((int)dstr.size() == 1, "Parse error: %s", dstr.c_str());
        char d = dstr[0];
        ensuref(d >= 'A' && d <= 'Z', "Out of range: %s", dstr.c_str());
        int p = ouf.readInt(0, n - 1, "p");
        if ((long long)ops.size() + 1 > 4LL * n * n) {
            quitf(_wa, "Too many operations");
        }
        ops.emplace_back(d, p);
    }
    return ops;
}

static void applyOp(vector<string>& cs, char d, int p) {
    int n = (int)cs.size();
    switch (d) {
        case 'L': {
            int i = p;
            for (int j = 0; j < n - 1; j++) cs[i][j] = cs[i][j + 1];
            cs[i][n - 1] = '.';
        } break;
        case 'R': {
            int i = p;
            for (int j = n - 1; j >= 1; j--) cs[i][j] = cs[i][j - 1];
            cs[i][0] = '.';
        } break;
        case 'U': {
            int j = p;
            for (int i = 0; i < n - 1; i++) cs[i][j] = cs[i + 1][j];
            cs[n - 1][j] = '.';
        } break;
        case 'D': {
            int j = p;
            for (int i = n - 1; i >= 1; i--) cs[i][j] = cs[i - 1][j];
            cs[0][j] = '.';
        } break;
        default:
            quitf(_wa, "Invalid direction: %c", d);
    }
}

static long long computeScore(const InputData& input, const vector<pair<char, int>>& out) {
    int n = input.n;
    vector<string> cs = input.cs;
    for (auto [d, p] : out) {
        applyOp(cs, d, p);
    }
    long long T = (long long)out.size();
    long long X = 0;
    long long Y = 2LL * n;
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            if (cs[i][j] == 'x') X++;
            if (cs[i][j] == 'o') Y--;
        }
    }
    long long score;
    if (X == 0 && Y == 0) {
        score = 8LL * n * n - T;
    } else {
        score = 4LL * n * n - 1LL * n * (X + Y);
    }
    return score;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    InputData input = parseInput();
    vector<pair<char, int>> ops;
    // Parse contestant output; any parse error will quit with WA inside parseOutput.
    ops = parseOutput(input.n);
    // Compute score
    long long score = computeScore(input, ops);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}