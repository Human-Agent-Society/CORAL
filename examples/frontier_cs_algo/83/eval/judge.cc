#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read n from input file
    int n = inf.readInt();

    // Read contestant answer f_user
    vector<int> f_user(n + 1);
    for (int i = 1; i <= n; ++i) {
        f_user[i] = ouf.readInt();
        if (abs(f_user[i]) != 1)
            quitf(_wa, "f_user(%d) = %d, |f(i)| must be 1", i, f_user[i]);
    }
    ouf.ensuref(ouf.seekEof(), "Extra output after %d numbers", n);

    // Read standard answer f_std
    vector<int> f_std(n + 1);
    for (int i = 1; i <= n; ++i) {
        f_std[i] = ans.readInt();
        if (abs(f_std[i]) != 1)
            quitf(_fail, "Invalid standard output: f_std(%d) = %d", i, f_std[i]);
    }

    // Verify multiplicativity: f(xy) = f(x)*f(y)
    // Complexity O(n log n) (enumerate multiples)
    for (int x = 1; x <= n; ++x) {
        for (int xy = x, y = 1; xy <= n; ++y, xy += x) {
            if (f_user[xy] != f_user[x] * f_user[y])
                quitf(_wa, "Not multiplicative: f(%d*%d)=%d, but f(%d)*f(%d)=%d",
                      x, y, f_user[xy], x, y, f_user[x]*f_user[y]);
        }
    }

    // Calculate prefix sum magnitude (user)
    long long s_user = 0, M_user = 0;
    for (int i = 1; i <= n; ++i) {
        s_user += f_user[i];
        M_user = max(M_user, llabs(s_user));
    }

    // Calculate prefix sum magnitude (standard answer)
    long long s_std = 0, M_std = 0;
    for (int i = 1; i <= n; ++i) {
        s_std += f_std[i];
        M_std = max(M_std, llabs(s_std));
    }

    // Prevent gaming the metric by making it smaller
    if (M_user == 0)
        quitf(_fail, "User M=0 (impossible)");

    double ratio = (double)M_std / (double)M_user;
    double unbounded_ratio = max(0.0, ratio);
    double score = max(0.0, min(1.0, ratio));

    quitp(score, "User M=%lld, Std M=%lld, Ratio: %.4f, RatioUnbounded: %.4f", M_user, M_std, score, unbounded_ratio);
}
