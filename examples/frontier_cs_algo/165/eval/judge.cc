#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct InputData {
    int n, m;
    int si, sj;
    vector<string> a;
    vector<string> t;
};

static bool is_uppercase_str(const string& s) {
    for (char c : s) if (!(c >= 'A' && c <= 'Z')) return false;
    return true;
}

static long long compute_score(const InputData& in, const vector<pair<int,int>>& out) {
    long long cost = 0;
    int pr = in.si, pc = in.sj;
    string S;
    S.reserve(out.size());

    for (auto [r, c] : out) {
        cost += llabs(pr - r) + llabs(pc - c) + 1;
        pr = r; pc = c;
        S.push_back(in.a[r][c]);
    }

    int K = 0;
    for (const string& w : in.t) {
        if (S.find(w) != string::npos) ++K;
    }

    if (K == in.m) {
        long long sc = 10000 - cost;
        if (sc < 1001) sc = 1001;
        return sc;
    } else {
        double val = 1000.0 * double(K + 1) / double(in.m);
        long long sc = llround(val);
        return sc;
    }
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Parse input
    InputData in;
    in.n = inf.readInt();
    in.m = inf.readInt();
    in.si = inf.readInt(0, in.n - 1);
    in.sj = inf.readInt(0, in.n - 1);

    in.a.resize(in.n);
    for (int i = 0; i < in.n; ++i) {
        in.a[i] = inf.readToken();
        ensuref((int)in.a[i].size() == in.n, "Grid row %d must have length %d", i, in.n);
        ensuref(is_uppercase_str(in.a[i]), "Grid row %d must contain only uppercase letters", i);
    }

    in.t.resize(in.m);
    for (int k = 0; k < in.m; ++k) {
        in.t[k] = inf.readToken();
        ensuref((int)in.t[k].size() == 5, "t[%d] must have length 5", k);
        ensuref(is_uppercase_str(in.t[k]), "t[%d] must contain only uppercase letters", k);
    }

    // Parse output
    vector<pair<int,int>> out;
    out.reserve(5000);
    while (!ouf.seekEof()) {
        int r = ouf.readInt(0, in.n - 1);
        int c = ouf.readInt(0, in.n - 1);
        out.emplace_back(r, c);
        if (out.size() > 5000u) {
            quitf(_wa, "Too many output moves: %zu > 5000", out.size());
        }
    }

    // Compute score
    long long score = compute_score(in, out);

    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();

    double score_ratio = max(0.0, min(1.0, (double)(score - baseline_value) / (best_value - baseline_value)));
    double unbounded_ratio = max(0.0, (double)(score - baseline_value) / (best_value - baseline_value));
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, unbounded_ratio);
}