#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    int n = inf.readInt();
    int m = inf.readInt();
    int k = inf.readInt();

    vector<string> cur(n);
    for (int i = 0; i < n; i++) {
        cur[i] = inf.readToken();
        if ((int)cur[i].size() != m)
            quitf(_fail, "initial row %d has wrong length", i + 1);
    }

    vector<string> target(n);
    for (int i = 0; i < n; i++) {
        target[i] = inf.readToken();
        if ((int)target[i].size() != m)
            quitf(_fail, "target row %d has wrong length", i + 1);
    }

    struct Preset { int r, c; vector<string> mat; };
    vector<Preset> pres(k + 1);
    for (int p = 1; p <= k; p++) {
        int rp = inf.readInt();
        int cp = inf.readInt();
        Preset pr; pr.r = rp; pr.c = cp; pr.mat.resize(rp);
        for (int i = 0; i < rp; i++) {
            pr.mat[i] = inf.readToken();
            if ((int)pr.mat[i].size() != cp)
                quitf(_fail, "preset %d row %d wrong length", p, i + 1);
        }
        pres[p] = std::move(pr);
    }

    if (ouf.seekEof())
        quitf(_pe, "empty output");

    // Data is guaranteed to have a solution; if -1 or negative, judge as wrong
    long long r = ouf.readLong();
    if (r < 0) quitf(_wa, "negative number of operations or -1 printed");
    if (r > 500000LL)
        quitf(_wa, "number of operations %lld exceeds limit 500000", r);

    long long presetCnt = 0;

    for (long long step = 0; step < r; step++) {
        int op = ouf.readInt(); // {-4,-3,-2,-1,0} or {1..k}
        int x = ouf.readInt();
        int y = ouf.readInt();

        if (op == -4) {
            if (!(1 < x && x <= n && 1 <= y && y <= m))
                quitf(_wa, "step %lld: invalid -4 position (%d,%d)", step + 1, x, y);
            swap(cur[x-1][y-1], cur[x-2][y-1]);
        } else if (op == -3) {
            if (!(1 <= x && x < n && 1 <= y && y <= m))
                quitf(_wa, "step %lld: invalid -3 position (%d,%d)", step + 1, x, y);
            swap(cur[x-1][y-1], cur[x][y-1]);
        } else if (op == -2) {
            if (!(1 <= x && x <= n && 1 < y && y <= m))
                quitf(_wa, "step %lld: invalid -2 position (%d,%d)", step + 1, x, y);
            swap(cur[x-1][y-1], cur[x-1][y-2]);
        } else if (op == -1) {
            if (!(1 <= x && x <= n && 1 <= y && y < m))
                quitf(_wa, "step %lld: invalid -1 position (%d,%d)", step + 1, x, y);
            swap(cur[x-1][y-1], cur[x-1][y]);
        } else if (op == 0) {
            if (!(1 <= x && x < n && 1 <= y && y < m))
                quitf(_wa, "step %lld: invalid rotate position (%d,%d)", step + 1, x, y);
            // clockwise rotate 2x2 at (x,y)
            char a = cur[x-1][y-1];
            char b = cur[x-1][y];
            char c = cur[x][y];
            char d = cur[x][y-1];
            cur[x-1][y] = a;
            cur[x][y] = b;
            cur[x][y-1] = c;
            cur[x-1][y-1] = d;
        } else {
            if (!(1 <= op && op <= k))
                quitf(_wa, "step %lld: invalid op %d", step + 1, op);
            presetCnt++;
            if (presetCnt > 400)
                quitf(_wa, "more than 400 preset operations");
            const Preset &P = pres[op];
            int rp = P.r, cp = P.c;
            if (!(1 <= x && x + rp - 1 <= n && 1 <= y && y + cp - 1 <= m))
                quitf(_wa, "step %lld: preset %d out of bounds at (%d,%d)", step + 1, op, x, y);
            for (int i = 0; i < rp; i++)
                for (int j = 0; j < cp; j++)
                    cur[x - 1 + i][y - 1 + j] = P.mat[i][j];
        }
    }

    ouf.skipBlanks();
    if (!ouf.seekEof())
        quitf(_pe, "extra data at the end of output");

    for (int i = 0; i < n; i++) {
        if (cur[i] != target[i])
            quitf(_wa, "final board does not match target at row %d", i + 1);
    }

    if (presetCnt > 400)
        quitf(_wa, "more than 400 preset operations");

    // Scoring: 10,000 -> 100; 500,000 -> 0 (linear)
    double score;
    const double L = 10000.0;
    const double R = 500000.0;
    double unbounded_score = max(0.0, R - r) / (R - L) * 100.0;
    if (r <= (long long)L) score = 100.0;
    else score = max(0.0, 100.0 * (R - r) / (R - L));

    double res = score / 100.0;
    quitp(res, "Ratio: %.4f, RatioUnbounded: %.4f", res, unbounded_score / 100.0);
}
