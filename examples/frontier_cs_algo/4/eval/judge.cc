#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static inline void flush_out(){ cout << flush; }

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    long long k; int n, type;
    n = inf.readInt();
    k = inf.readLong();
    type = inf.readInt();
    long long QUERY_LIMIT=inf.readLong();
    vector<long long> flat; flat.reserve(1LL * n * n);
    vector<vector<long long>> A(n, vector<long long>(n));

    if (type == 0) {
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++) {
                long long v = inf.readLong();
                flat.push_back(v);
                A[i][j] = v;
            }
    } else {
        auto val = [&](int x, int y)->long long {
            if (type == 1) return x + y;
            if (type == 2) return 1LL * x * y;
            if (type == 3) return 1LL * (x + n) * (y + n);
            if (type == 4) return x + 2LL * y;
            if (type == 5) return 2LL * x + y;
            return 0LL;
        };
        for (int i = 1; i <= n; i++)
            for (int j = 1; j <= n; j++) {
                long long v = val(i, j);
                flat.push_back(v);
                A[i - 1][j - 1] = v;
            }
    }

    if (k < 1 || k > (long long)flat.size()) {
        quitf(_fail, "Bad test data: k=%lld out of [1,%lld]", k, (long long)flat.size());
    }

    long long correct = ans.readLong();

    // Send public parameters to the contestant
    println(n, k);
    flush_out();
    auto start = chrono::steady_clock::now();
    long long used = 0;
    while (true) {
        if (ouf.seekEof()) {
            quitp(0.0, "Unexpected EOF without DONE");
        }
        string op = ouf.readToken(); // Read operation

        if (op == "QUERY") {
            int x = ouf.readInt();
            int y = ouf.readInt();
            if (x < 1 || x > n || y < 1 || y > n) {
                quitp(0.0, "Query Out of Bound");
            }
            if (++used > QUERY_LIMIT) {
                quitp(0.0, "Query Limit Exceed");
            }
            println(A[x - 1][y - 1]);
            flush_out();
        } else if (op == "DONE") {
            auto end = chrono::steady_clock::now();
            double elapsed = chrono::duration<double>(end - start).count();

            cerr << "[Interactor] time used = " << elapsed << " s\n";
            long long user_ans = ouf.readLong();
            if (user_ans != correct) {
                quitp(0.0, "Wrong Guess");
            }
            double score = 0.0;
            long long B = n; 
            if (used <= B) score = 1.0;
            else if (used >= QUERY_LIMIT) score = 0.0;
            else score = double(QUERY_LIMIT - used) / double(QUERY_LIMIT - B);

            double unbounded_score = 0.0;
            if (used >= QUERY_LIMIT) unbounded_score = 0.0;
            else unbounded_score = double(QUERY_LIMIT - used) / double(QUERY_LIMIT - B);

            cerr << "[Interactor] used=" << used << "\n";
            quitp(score, "Correct Guess. Ratio: %.4f, RatioUnbounded: %.4f", score, unbounded_score);
        } else {
            quitf(_wa, "Invalid Action Type: %s", op.c_str());
        }
    }
}
