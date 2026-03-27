#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    int n = inf.readInt(1, 30000, "n");
    cout << n << endl;
    cout.flush();

    // === ���ɷ������������ ===
    vector<int> a(n);
    iota(a.begin(), a.end(), 1);
    for (int i = 0; i < n; i++) {
        int l = i;
        int r = min(n - 1, i + 2);
        int j = rnd.next(l, r); // pick j uniformly in [i, min(n-1, i+2)]
        swap(a[i], a[j]);
    }

    const int limit = n * 5 / 3 + 5;
    int queries = 0;

    while (true) {
    	string cmd;
        try {
            cmd = ouf.readWord();  // ? �ĳ� readWord()
        } catch (...) {
            quitf(_fail, "Unexpected EOF or invalid token while reading command.");
        }

        if (cmd == "?") {
            ++queries;
            if (queries > limit) {
                quitf(_wa, "Too many queries (%d > %d)", queries, limit);
            }

            int i = ouf.readInt(1, n, "i");
            int j = ouf.readInt(1, n, "j");
            if (i == j)
                quitf(_wa, "Queried identical indices (%d == %d)", i, j);

            if (a[i - 1] < a[j - 1])
                cout << "<" << endl;
            else
                cout << ">" << endl;
            cout.flush();
        }
        else if (cmd == "!") {
			vector<int> b(n);
			for (int i = 0; i < n; ++i)
			    b[i] = ouf.readInt(1, n, "a[i]");
            set<int> s(b.begin(), b.end());
            if ((int)s.size() != n)
                quitf(_wa, "Array is not a permutation.");

            if (b != a)
                quitf(_wa, "Wrong final array.");

            // === ƽ����ֲ��� ===
            // 0 �� queries �� limit
            // queries=0 -> 1.0, queries=limit -> 0.8
            double ratio = 0.8 + 0.2 * (1.0 - (double)queries / limit);
            double ratio_unbounded = 0.8 * limit / queries;
            ratio = max(0.2, min(1.0, ratio));

            double score = ratio * 100.0, score_unbounded = ratio_unbounded * 100.0;

            string msg = format(
                "Correct! Queries = %d (limit = %d). Ratio: %.6f (Score: %.2f). RatioUnbounded: %.6f (ScoreUnbounded: %.2f)",
                queries, limit, ratio, score, ratio_unbounded, score_unbounded);

            quitp(ratio, msg.c_str());
        }
        else {
            quitf(_wa, "Unexpected command: %s", cmd.c_str());
        }
    }
}

