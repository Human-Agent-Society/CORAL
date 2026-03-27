#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct State {
    int px, py; // player
    int bx, by; // box top-left
};

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read contestant output.
    int N = ouf.readInt(1, 100, "N");
    ouf.readSpace();
    int M = ouf.readInt(1, 100, "M");
    ouf.readEoln();

    if (N + M > 100) {
        quitf(_wa, "N + M must be <= 100, but got N=%d, M=%d", N, M);
    }

    vector<string> g(N);
    for (int i = 0; i < N; ++i) {
        g[i] = ouf.readToken(format("[.#PBS]{%d}", M), "grid row");
        if ((int)g[i].size() != M) {
            quitf(_pe, "Row %d has wrong length: expected %d, got %d", i + 1, M, (int)g[i].size());
        }
        ouf.readEoln(); // force end of line
    }
    // Be lenient with trailing blanks, then require EOF.
    ouf.skipBlanks();
    if (!ouf.seekEof()) {
        quitf(_pe, "Expected EOF, but found extra non-space characters at the end");
    }

    int px = -1, py = -1;
    int bminx = N, bminy = M, bmaxx = -1, bmaxy = -1, cntB = 0;
    int sminx = N, sminy = M, smaxx = -1, smaxy = -1, cntS = 0;
    int cntP = 0;

    vector<vector<int>> wall(N, vector<int>(M, 0));

    for (int i = 0; i < N; ++i) {
        for (int j = 0; j < M; ++j) {
            char c = g[i][j];
            if (c == '#') {
                wall[i][j] = 1;
            } else if (c == 'P') {
                cntP++;
                px = i; py = j;
            } else if (c == 'B') {
                cntB++;
                bminx = min(bminx, i);
                bmaxx = max(bmaxx, i);
                bminy = min(bminy, j);
                bmaxy = max(bmaxy, j);
            } else if (c == 'S') {
                cntS++;
                sminx = min(sminx, i);
                smaxx = max(smaxx, i);
                sminy = min(sminy, j);
                smaxy = max(smaxy, j);
            } else if (c == '.') {
                // empty
            } else {
                quitf(_pe, "Invalid character '%c' at (%d,%d)", c, i + 1, j + 1);
            }
        }
    }

    if (cntP != 1) {
        quitf(_wa, "Grid must contain exactly one player P, but got %d", cntP);
    }
    if (cntB != 4) {
        quitf(_wa, "Grid must contain exactly four 'B' cells, but got %d", cntB);
    }
    if (cntS != 4) {
        quitf(_wa, "Grid must contain exactly four 'S' cells, but got %d", cntS);
    }
    if (px == -1) {
        quitf(_wa, "Player position not found");
    }
    if (bmaxx < bminx || bmaxy < bminy) {
        quitf(_wa, "Box cells not found correctly");
    }
    if (smaxx < sminx || smaxy < sminy) {
        quitf(_wa, "Storage cells not found correctly");
    }

    int boxH = bmaxx - bminx + 1;
    int boxW = bmaxy - bminy + 1;
    int goalH = smaxx - sminx + 1;
    int goalW = smaxy - sminy + 1;

    if (boxH != 2 || boxW != 2) {
        quitf(_wa, "Box must form a 2x2 square, but its bounding box is %dx%d", boxH, boxW);
    }
    if (goalH != 2 || goalW != 2) {
        quitf(_wa, "Storage must form a 2x2 square, but its bounding box is %dx%d", goalH, goalW);
    }

    int bx0 = bminx, by0 = bminy;
    int gx = sminx, gy = sminy;

    // Player must be on empty
    if (wall[px][py]) {
        quitf(_wa, "Player is on a wall");
    }

    auto inside = [&](int x, int y) {
        return 0 <= x && x < N && 0 <= y && y < M;
    };
    auto inBox = [&](int x, int y, int bx, int by) {
        return (bx <= x && x < bx + boxH && by <= y && y < by + boxW);
    };
    auto boxOk = [&](int bx, int by) {
        if (bx < 0 || by < 0 || bx + boxH > N || by + boxW > M) return false;
        for (int i = 0; i < boxH; ++i)
            for (int j = 0; j < boxW; ++j)
                if (wall[bx + i][by + j]) return false;
        return true;
    };

    if (!boxOk(bx0, by0)) {
        quitf(_wa, "Initial box position overlaps wall or is out of bounds");
    }

    // Box and storage must not overlap initially
    for (int i = 0; i < boxH; ++i) {
        for (int j = 0; j < boxW; ++j) {
            int bx = bx0 + i, by = by0 + j;
            int sx = gx + i, sy = gy + j;
            if (bx == sx && by == sy) {
                quitf(_wa, "Box and storage location must not intersect initially");
            }
        }
    }

    if (inBox(px, py, bx0, by0)) {
        quitf(_wa, "Player starts inside the box");
    }

    int BN = N - boxH + 1;
    int BM = M - boxW + 1;
    if (BN <= 0 || BM <= 0) {
        quitf(_wa, "Grid is too small for a 2x2 box");
    }

    auto idx = [&](int px, int py, int bx, int by) {
        int bi = bx * BM + by; // box index
        return ((bi * N + px) * M + py);
    };

    int totalStates = N * M * BN * BM;
    vector<int> dist(totalStates, -1);
    queue<State> q;

    State start{px, py, bx0, by0};
    int startId = idx(px, py, bx0, by0);
    dist[startId] = 0;
    q.push(start);

    const int dx[4] = {-1, 1, 0, 0};
    const int dy[4] = {0, 0, -1, 1};

    int bestMoves = -1;

    while (!q.empty()) {
        State cur = q.front(); q.pop();
        int curId = idx(cur.px, cur.py, cur.bx, cur.by);
        int d = dist[curId];

        // Goal: box top-left equals storage top-left
        if (cur.bx == gx && cur.by == gy) {
            bestMoves = d;
            break;
        }

        for (int dir = 0; dir < 4; ++dir) {
            int npx = cur.px + dx[dir];
            int npy = cur.py + dy[dir];
            if (!inside(npx, npy)) continue;
            if (wall[npx][npy]) continue;

            if (!inBox(npx, npy, cur.bx, cur.by)) {
                // Just move the player
                int nid = idx(npx, npy, cur.bx, cur.by);
                if (dist[nid] == -1) {
                    dist[nid] = d + 1;
                    q.push({npx, npy, cur.bx, cur.by});
                }
            } else {
                // Push the box
                int nbx = cur.bx + dx[dir];
                int nby = cur.by + dy[dir];
                if (!boxOk(nbx, nby)) continue;

                int nid = idx(npx, npy, nbx, nby);
                if (dist[nid] == -1) {
                    dist[nid] = d + 1;
                    q.push({npx, npy, nbx, nby});
                }
            }
        }
    }

    if (bestMoves < 0) {
        quitf(_wa, "The puzzle is unsolvable");
    }


    long long score = bestMoves;
    double score_ratio = bestMoves <= 0 ? 0.0 : (double)bestMoves / 63000.0;
    double unbounded_ratio = score_ratio;
    if (score_ratio > 1.0) score_ratio = 1.0;

    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}
