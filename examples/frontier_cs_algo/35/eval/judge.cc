#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

double f_bounded(int x) {
    if (x <= 500) return 100.0;
    if (x >= 5000) return 0.0;
    return 100.0 * (5000.0 - x) / (5000.0 - 500.0);
}

double f_unbounded(int x) {
    if (x >= 5000) return 0.0;
    return 100.0 * (5000.0 - x) / (5000.0 - 500.0);
}

int a[605], t[305];

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    const int T = 20;
    cout << T << endl;

    double best_bounded = 100.0;
    double best_unbounded = 100.0;
    int mxq = 0;

    uint32_t seed = static_cast<uint32_t>(
        chrono::steady_clock::now().time_since_epoch().count()
    );
    std::mt19937 rnd(seed);

    for (int tc = 0; tc < T; tc++) {
        int n = 300;
        int pos = static_cast<int>(rnd() % n) + 1;

        int tot = 0;
        for (int i = 1; i <= n; i++) a[++tot] = i;
        for (int i = 1; i < pos; i++) a[++tot] = i;
        for (int i = pos + 1; i <= n; i++) a[++tot] = i;
        assert(tot == 2 * n - 1);
        shuffle(a + 1, a + tot + 1, rnd);

        cout << n << endl;

        int queries = 0;
        while (true) {
            string op = ouf.readToken();
            if (op == "?") {
                int x = ouf.readInt(1, n, "x");
                int m = ouf.readInt(1, 2 * n - 1, "m");
                bool flag = false;
                for (int i = 1; i <= m; i++) {
                    int nw = ouf.readInt(1, 2 * n - 1, "idx");
                    if (a[nw] == x) flag = true;
                }
                cout << (flag ? 1 : 0) << endl;
                queries++;
                if (queries > 5000) quitf(_wa, "Too many queries (>5000)");
            } else if (op == "!") {
                int x = ouf.readInt(1, n, "answer");
                if (x != pos) {
                    quitf(_wa, "wrong position on test %d: expected %d, got %d",
                          tc + 1, pos, x);
                }
                double sc_b = f_bounded(queries);
                double sc_u = f_unbounded(queries);
                best_bounded = min(best_bounded, sc_b);
                best_unbounded = min(best_unbounded, sc_u);
                mxq = max(mxq, queries);
                break;
            } else {
                quitf(_pe, "unknown command '%s' on test %d", op.c_str(), tc + 1);
            }
        }
    }

    double ratio = best_bounded / 100.0;
    double ratio_unbounded = best_unbounded / 100.0;

    quitp(ratio, "all %d tests passed; Ratio: %.4f; RatioUnbounded: %.4f; mxq = %d",
          T, ratio, ratio_unbounded, mxq);
    return 0;
}
