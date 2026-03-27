// chk_grid.cc
#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const int H = 8;
static const int W = 14;
static const int N = H * W;

// Precomputed 8-neighborhood (no "stay" moves)
static vector<int> NEIGH[N];

static inline void buildNeighbors() {
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            int i = y * W + x;
            for (int dy = -1; dy <= 1; ++dy)
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0) continue;
                    int ny = y + dy, nx = x + dx;
                    if (0 <= ny && ny < H && 0 <= nx && nx < W) {
                        NEIGH[i].push_back(ny * W + nx);
                    }
                }
        }
    }
}

static void ensureDigitRow(const string& row, int rowId, const char* who) {
    if ((int)row.size() != W) {
        if (string(who) == "participant")
            quitp(0.0, "Row %d must have exactly %d characters, got %d. Score=0.0",
                  rowId + 1, W, (int)row.size());
        quitf(_fail, "Answer file: row %d must have exactly %d characters, got %d.",
              rowId + 1, W, (int)row.size());
    }
    for (char ch : row) {
        if (ch < '0' || ch > '9') {
            if (string(who) == "participant")
                quitp(0.0, "Row %d contains a non-digit character '%c'. Score=0.0",
                      rowId + 1, ch);
            quitf(_fail, "Answer file: row %d contains a non-digit character '%c'.",
                  rowId + 1, ch);
        }
    }
}

// Read exactly 8 lines of 14 digits from ans.txt (NO header line)
static vector<string> readAnswerGrid(InStream& S) {
    vector<string> g;
    g.reserve(H);
    for (int r = 0; r < H; ++r) {
        if (S.seekEof())
            quitf(_fail, "Answer file: expected %d rows, got %d.", H, r);
        string row = S.readToken();
        ensureDigitRow(row, r, "answer");
        g.push_back(row);
    }
    // Extra tokens, if any, are ignored (no readEof requirement).
    return g;
}

// Read exactly 8 lines of 14 digits from out.txt
static vector<string> readParticipantGrid(InStream& S) {
    vector<string> g(H);
    for (int r = 0; r < H; ++r) {
        if (S.seekEof()) {
            quitp(0.0, "Not enough rows in output: expected %d lines, got %d. Score=0.0", H, r);
        }
        g[r] = S.readToken();
        ensureDigitRow(g[r], r, "participant");
    }
    // Any extra tokens are ignored (no readEof requirement).
    return g;
}

// Convert grid to flat char vector and index positions by digit
struct GridIndex {
    array<vector<int>, 10> posByDigit;
    vector<char> flat; // size N, digits '0'..'9'
};
static GridIndex indexGrid(const vector<string>& g) {
    GridIndex idx;
    idx.flat.resize(N);
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            char ch = g[y][x];
            idx.flat[y * W + x] = ch;
            idx.posByDigit[ch - '0'].push_back(y * W + x);
        }
    }
    return idx;
}

// Check if a decimal string s can be read on the grid (revisits allowed, 8-dir moves, no "stay")
static bool canRead(const GridIndex& G, const string& s) {
    int L = (int)s.size();
    int d0 = s[0] - '0';
    const vector<int>& starts = G.posByDigit[d0];
    if (starts.empty()) return false;

    vector<int> frontier = starts;
    vector<char> nextMark(N, 0);

    for (int pos = 1; pos < L; ++pos) {
        int need = s[pos] - '0';
        vector<int> next;
        for (int u : frontier) {
            for (int v : NEIGH[u]) {
                if (!nextMark[v] && G.flat[v] - '0' == need) {
                    nextMark[v] = 1;
                    next.push_back(v);
                }
            }
        }
        if (next.empty()) return false;
        fill(nextMark.begin(), nextMark.end(), 0);
        frontier.swap(next);
    }
    return true;
}

// Compute the TRUE prefix score: largest X with all numbers 1..X readable.
// If capX >= 0, stop early and return min(realScore, capX).
static long long prefixScore(const GridIndex& G, long long capX = -1) {
    long long X = 0;
    for (long long k = 1; ; ++k) {
        if (capX >= 0 && k > capX) return capX;
        string s = to_string(k);
        if (canRead(G, s)) X = k;
        else return X;
    }
}

// Optional quick file check
static void checkAnsFileIsNotEmpty(const char* path) {
    ifstream f(path, ios::binary);
    if (!f) quitf(_fail, "Cannot open %s", path);
    f.seekg(0, ios::end);
    if (f.tellg() == 0) quitf(_fail, "ans.txt is empty (0 bytes) inside sandbox.");
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    if (argc < 4) {
        quitf(_fail, "Usage: %s in.txt out.txt ans.txt", argv[0]);
    }

    checkAnsFileIsNotEmpty(argv[3]);
    buildNeighbors();

    // We do NOT read anything from in.txt and there is NO header in ans.txt.

    // Jury (best-known) grid
    vector<string> bestGrid = readAnswerGrid(ans);
    GridIndex Gbest = indexGrid(bestGrid);
    long long Best = prefixScore(Gbest);

    // Participant grid
    vector<string> yourGrid = readParticipantGrid(ouf);
    GridIndex Gyour = indexGrid(yourGrid);

    // Cap participant evaluation at Best (ratio is clamped to [0,1] anyway)
    long long Your = prefixScore(Gyour, /*capX=*/Best);

    double ratio = (Best == 0 ? 0.0 : (double)Your / (double)Best);
    if (ratio < 0) ratio = 0;
    double unbounded_ratio = max(0.0, ratio);
    if (ratio > 1) ratio = 1;

    quitp(ratio, "Valid grid. Your=%lld Best=%lld Ratio: %.8f, RatioUnbounded: %.8f", Your, Best, ratio, unbounded_ratio);
}
