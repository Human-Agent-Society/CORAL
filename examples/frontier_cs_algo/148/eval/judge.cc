#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int N = 50;

// This function is no longer needed, as readToken() handles trimming.
// static inline string trim_copy(const string& s) { ... }

// This function now takes testlib streams instead of file paths
long long compute_score(InStream& inf, InStream& ouf) {
    // Read input file fully using inf
    long long si, sj;
    si = inf.readLong();
    sj = inf.readLong();

    vector<vector<long long>> tiles(N, vector<long long>(N));
    vector<vector<long long>> ps(N, vector<long long>(N));

    long long maxTile = -1;
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            tiles[i][j] = inf.readLong(); // Use inf
            if (tiles[i][j] < 0) quitf(_wa, "tile id negative");
            if (tiles[i][j] > maxTile) maxTile = tiles[i][j];
        }
    }
    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < N; ++j) {
            ps[i][j] = inf.readLong(); // Use inf
        }
    }

    // --- FIX IS HERE ---
    // Read the entire output (which is one string) using ouf.readToken()
    string out;
    try {
        out = ouf.readToken();
    } catch (...) {
        // Handle empty output (which is valid)
        out = "";
    }
    // We must ensure there is no other text in the file
    ouf.seekEof(); 
    // --- END FIX ---

    // Validate characters.
    for (char c : out) {
        if (c != 'L' && c != 'R' && c != 'U' && c != 'D') {
            quitf(_wa, "Illegal output");
        }
    }

    // Prepare used array
    long long usedSize = max(maxTile + 1, (long long)N * (long long)N);
    vector<long long> used(usedSize, 0);

    // Simulate path
    long long i = si, j = sj;
    if (i < 0 || i >= N || j < 0 || j >= N) quitf(_wa, "Out of range");
    used[tiles[i][j]] = 1;
    long long score = ps[i][j];
    bool hasError = false;
    string errMsg;

    for (char c : out) {
        long long di = 0, dj = 0;
        if (c == 'L') { di = 0; dj = -1; }
        else if (c == 'R') { di = 0; dj = 1; }
        else if (c == 'U') { di = -1; dj = 0; }
        else if (c == 'D') { di = 1; dj = 0; }
        else {
            quitf(_wa, "Illegal output");
        }
        i += di; j += dj;
        if (i < 0 || i >= N || j < 0 || j >= N) {
            quitf(_wa, "Out of range");
        }
        if (tiles[i][j] < 0 || tiles[i][j] >= usedSize) {
            quitf(_fail, "tile id out of bounds");
        }
        if (used[tiles[i][j]] != 0) {
            hasError = true;
            errMsg = "Stepped on the same tile twice";
        }
        used[tiles[i][j]] += 1;
        score += ps[i][j];
    }

    if (hasError) {
        quitf(_wa, "%s", errMsg.c_str());
    }

    return score;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    long long score = 0;
    try {
        // Pass the standard testlib streams
        score = compute_score(inf, ouf);
    } catch (...) {
        quitf(_wa, "error");
    }
    
    // This part remains the same
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}