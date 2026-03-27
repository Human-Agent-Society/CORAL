#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct UnionFind {
    int n;
    vector<int> p; // negative size for root, parent otherwise
    UnionFind(int n = 0): n(n), p(n, -1) {}
    int find(int x) {
        if (p[x] < 0) return x;
        return p[x] = find(p[x]);
    }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (-p[a] < -p[b]) swap(a, b);
        p[a] += p[b];
        p[b] = a;
        return true;
    }
    bool same(int a, int b) { return find(a) == find(b); }
    int size(int x) { return -p[find(x)]; }
};

// Function now takes testlib streams
static long long compute_score(InStream& inf, InStream& ouf) {
    // Read input using inf
    long long N = inf.readLong();
    long long T = inf.readLong();

    vector<string> rows(N);
    for (long long i = 0; i < N; i++) {
        rows[i] = inf.readToken();
        if ((long long)rows[i].size() != N) quitf(_fail, "row length mismatch at row %lld", i);
    }
    // No fin.close() needed

    // Parse tiles
    auto hexval = [](char c) -> int {
        if ('0' <= c && c <= '9') return c - '0';
        if ('a' <= c && c <= 'f') return 10 + (c - 'a');
        if ('A' <= c && c <= 'F') return 10 + (c - 'A');
        return -1;
    };
    vector<vector<int>> tiles(N, vector<int>(N, 0));
    long long bi = -1, bj = -1;
    for (long long i = 0; i < N; i++) {
        for (long long j = 0; j < N; j++) {
            int v = hexval(rows[i][j]);
            if (v < 0) quitf(_fail, "invalid hex at (%lld,%lld)", i, j);
            tiles[i][j] = v;
            if (v == 0) { bi = i; bj = j; }
        }
    }
    if (bi == -1) quitf(_fail, "no empty tile found");

    // Read output (moves) using ouf
    string moves;
    try {
        moves = ouf.readToken(); // Reads the single block of moves, trimming whitespace.
    } catch (...) {
        // Handle empty output (which is valid)
        moves = "";
    }
    ouf.seekEof(); // Ensure no extra output
    // No fou.close() needed or whitespace removal loop

    // from mapping: for position (i,j), store original (i0,j0)
    vector<vector<pair<long long,long long>>> from(N, vector<pair<long long,long long>>(N));
    for (long long i = 0; i < N; i++) for (long long j = 0; j < N; j++) from[i][j] = {i, j};

    auto apply_move = [&](char c, long long turn, long long &ci, long long &cj) {
        long long di = 0, dj = 0;
        if (c == 'L') { di = 0; dj = -1; }
        else if (c == 'U') { di = -1; dj = 0; }
        else if (c == 'R') { di = 0; dj = 1; }
        else if (c == 'D') { di = 1; dj = 0; }
        else {
            quitf(_wa, "illegal move: %c (turn %lld)", c, turn);
        }
        long long ni = ci + di, nj = cj + dj;
        if (ni < 0 || ni >= N || nj < 0 || nj >= N) {
            quitf(_wa, "illegal move: %c (turn %lld)", c, turn);
        }
        auto f1 = from[ci][cj];
        auto f2 = from[ni][nj];
        from[ni][nj] = f1;
        from[ci][cj] = f2;
        ci = ni; cj = nj;
    };

    long long turn = 0;
    long long ci = bi, cj = bj;
    for (char c : moves) {
        apply_move(c, turn, ci, cj);
        turn++;
    }

    if (turn > T) {
        quitf(_wa, "too many moves");
    }

    // Reconstruct current tiles with mapping
    vector<vector<int>> cur(N, vector<int>(N, 0));
    for (long long i = 0; i < N; i++) {
        for (long long j = 0; j < N; j++) {
            auto pr = from[i][j];
            cur[i][j] = tiles[pr.first][pr.second];
        }
    }

    // Build graph via UnionFind
    UnionFind uf((int)(N * N));
    vector<char> tree(N * N, 1); // true initially
    auto id = [N](long long i, long long j) { return (int)(i * N + j); };

    for (long long i = 0; i < N; i++) {
        for (long long j = 0; j < N; j++) {
            if (i + 1 < N) {
                if ((cur[i][j] & 8) != 0 && (cur[i + 1][j] & 2) != 0) {
                    int a = uf.find(id(i, j));
                    int b = uf.find(id(i + 1, j));
                    if (a == b) {
                        tree[a] = 0;
                    } else {
                        char t = tree[a] && tree[b];
                        uf.unite(a, b);
                        int r = uf.find(a);
                        tree[r] = t;
                    }
                }
            }
            if (j + 1 < N) {
                if ((cur[i][j] & 4) != 0 && (cur[i][j + 1] & 1) != 0) {
                    int a = uf.find(id(i, j));
                    int b = uf.find(id(i, j + 1));
                    if (a == b) {
                        tree[a] = 0;
                    } else {
                        char t = tree[a] && tree[b];
                        uf.unite(a, b);
                        int r = uf.find(a);
                        tree[r] = t;
                    }
                }
            }
        }
    }

    int max_tree = -1;
    int max_size = -1;
    for (long long i = 0; i < N; i++) {
        for (long long j = 0; j < N; j++) {
            if (cur[i][j] != 0) {
                int r = uf.find(id(i, j));
                if (tree[r]) {
                    int sz = uf.size(id(i, j));
                    if (sz > max_size) {
                        max_size = sz;
                        max_tree = id(i, j);
                    }
                }
            }
        }
    }

    long long sizeLargest = (max_tree == -1) ? 0LL : (long long)uf.size(max_tree);
    long long totalTiles = N * N - 1;

    long long score;
    if (sizeLargest == totalTiles) {
        double val = 500000.0 * (1.0 + (double)(T - turn) / (double)T);
        score = llround(val);
    } else {
        double val = 500000.0 * (double)sizeLargest / (double)totalTiles;
        score = llround(val);
    }

    return score;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    // No longer read argv[1] or argv[2]
    
    long long score = compute_score(inf, ouf); // Pass testlib streams
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}