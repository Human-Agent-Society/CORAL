// chk.cc — Checker for "Distinct Pairwise XOR Set"
// Style: modeled after the knight-path checker; prints
// quitp(ratio, "Valid XOR set. Your=%d Best=%lld Ratio: %.8f", ...)
// Ratio = (size of participant set) / (size of best set from ans.txt)

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static bool readMaybeLong(InStream& S, long long &x){
    try { x = S.readLong(); return true; }
    catch(...) { return false; }
}
static bool readMaybeInt(InStream& S, int &x){
    try { x = S.readInt(); return true; }
    catch(...) { return false; }
}

// Compute K = ceil(log2(n+1)) so that all XORs of numbers in [1..n] fit in [0..2^K-1]
static int xorBitWidth(long long n){
    unsigned long long nu = (unsigned long long)max(1LL, n);
    int k = 64 - __builtin_clzll(nu); // ceil(log2(nu+?)), good for n>=1
    if ((1ULL << k) <= (unsigned long long)n) ++k; // ensure 2^k > n when n is exact power-1 edge
    return max(1, k);
}

struct ReadResult {
    vector<int> a;
    long long m = 0;
};

// Read "length-first" set:
// m
// v1 v2 ... vm
// who = "participant" or "answer"
static ReadResult readSetLenOnly(InStream& S, long long n, const char* who, bool allowZero){
    ReadResult R;
    long long m;
    if (!readMaybeLong(S, m)){
        if (string(who)=="participant") quitp(0.0, "Empty output (no m). Score=0.0");
        quitf(_fail, "Answer file is empty (no m).");
    }
    if (m < 0 || m > n){
        if (string(who)=="participant") quitp(0.0, "Invalid m=%lld. Score=0.0", m);
        quitf(_fail, "Answer file: invalid m=%lld.", m);
    }
    if (m == 0 && !allowZero){
        if (string(who)=="participant") quitp(0.0, "m=0 not allowed here. Score=0.0");
        quitf(_fail, "Answer file: m=0 not allowed.");
    }

    R.m = m;
    R.a.reserve((size_t)m);
    vector<unsigned char> used((size_t)n + 1, 0);

    for (long long i = 0; i < m; ++i){
        int x;
        if (!readMaybeInt(S, x)){
            if (string(who)=="participant") quitp(0.0, "Output ended before %lld numbers. Score=0.0", m);
            quitf(_fail, "Answer file: ended before %lld numbers.", m);
        }
        if (x < 1 || x > n){
            if (string(who)=="participant") quitp(0.0, "Number out of range at pos %lld: %d (need 1..%lld). Score=0.0", i+1, x, n);
            quitf(_fail, "Answer file: number out of range at pos %lld: %d (need 1..%lld).", i+1, x, n);
        }
        if (used[x]){
            if (string(who)=="participant") quitp(0.0, "Duplicate number: %d. Score=0.0", x);
            quitf(_fail, "Answer file: duplicate number: %d.", x);
        }
        used[x] = 1;
        R.a.push_back(x);
    }
    // Ignore any extra tokens after m numbers.
    return R;
}

static void checkXorDistinct(const vector<int>& a, long long n, const char* who){
    long long m = (long long)a.size();
    if (m <= 1) return; // vacuously distinct

    int K = xorBitWidth(n);
    long long cap = 1LL << K; // number of distinct XOR values available [0..2^K-1]
    long long pairs = m * (m - 1) / 2;

    // Quick impossibility check
    if (pairs > cap){
        if (string(who)=="participant")
            quitp(0.0, "Impossible: m=%lld yields %lld pairs > %lld available XORs. Score=0.0", m, pairs, cap);
        quitf(_fail, "Answer file: m=%lld yields %lld pairs > %lld available XORs.", m, pairs, cap);
    }

    vector<unsigned char> seen((size_t)cap, 0);
    for (long long i = 0; i < m; ++i){
        for (long long j = i + 1; j < m; ++j){
            int v = a[i] ^ a[j];
            if (seen[(size_t)v]){
                if (string(who)=="participant")
                    quitp(0.0, "XOR collision: a[%lld]=%d XOR a[%lld]=%d = %d already seen. Score=0.0",
                          i+1, a[i], j+1, a[j], v);
                quitf(_fail, "Answer file: XOR collision between indices %lld and %lld (value %d).", i+1, j+1, v);
            }
            seen[(size_t)v] = 1;
        }
    }
}

int main(int argc, char* argv[]){
    registerTestlibCmd(argc, argv);
    if (argc < 4) {
        quitf(_fail, "Usage: %s in.txt out.txt ans.txt", argv[0]);
    }

    // Optional: ensure ans.txt exists and is not 0 bytes
    {
        ifstream f(argv[3], ios::binary);
        if (!f) quitf(_fail, "Cannot open %s", argv[3]);
        f.seekg(0, ios::end);
        if (f.tellg() == 0) quitf(_fail, "ans.txt is empty (0 bytes).");
    }

    // Read input: n
    long long n;
    try { n = inf.readLong(1LL, 10000000LL, "n"); }
    catch(...) { quitf(_fail, "Failed to read valid n from input."); }

    // Read best (answer) and your (participant) sets
    auto best = readSetLenOnly(ans, n, "answer", /*allowZero=*/false);
    auto yours = readSetLenOnly(ouf, n, "participant", /*allowZero=*/true);

    // Validate XOR-distinctness for both
    checkXorDistinct(best.a, n, "answer");
    checkXorDistinct(yours.a, n, "participant");

    long long Best = best.m;
    int Your = (int)yours.m;

    double ratio = (Best == 0) ? 0.0 : (double)Your / (double)Best;
    if (ratio < 0) ratio = 0;
    double unbounded_ratio = max(0.0, ratio);
    if (ratio > 1) ratio = 1;

    quitp(ratio, "Valid XOR set. Your=%d Best=%lld Ratio: %.8f, RatioUnbounded: %.8f", Your, Best, ratio, unbounded_ratio);
}
