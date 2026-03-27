// checker.cc  — RSSP scorer using testlib
// Input format (inf):
//   n T
//   a_1 a_2 ... a_n
// Output format (ouf):
//   binary string of length n (0/1). Spaces/newlines are ignored.
// Score ratio = (18 - ln(error + 1)) / 18, clamped to [0,1].
// (Polygon will multiply by test points; if you want 0..100 in message, we print it too.)

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

using u128 = __uint128_t;
using u64  = unsigned long long;

// ---- u128 helpers ----
static bool parse_u128_str(const string &s, u128 &out) {
    if (s.empty()) return false;
    u128 v = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        v = v * 10 + (c - '0');
    }
    out = v;
    return true;
}
static string to_string_u128(u128 x) {
    if (x == 0) return "0";
    string s;
    while (x > 0) {
        int d = int(x % 10);
        s.push_back(char('0' + d));
        x /= 10;
    }
    reverse(s.begin(), s.end());
    return s;
}
// Convert u128 to long double without precision loss for ~1e24 range
static long double u128_to_ld(u128 x) {
    // split by 1e18 to stay exactly representable in long double (80-bit on most judges)
    const u128 BASE = (u128)1000000000000000000ULL; // 1e18
    u128 hi = x / BASE;
    u128 lo = x % BASE;
    long double ld = (long double)hi;
    ld *= 1e18L;
    ld += (long double)lo;
    return ld;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // Read n and T (T may exceed 64-bit, read as token then parse u128)
    long long n_ll = inf.readLong(1LL, 1000LL, "n");
    size_t n = (size_t)n_ll;
    string Ttok = inf.readToken("T");
    u128 T;
    if (!parse_u128_str(Ttok, T)) {
        quitf(_fail, "Invalid T token: '%s'", Ttok.c_str());
    }

    // Read a_i in [0, 1e18]
    const long long Bmax = 1000000000000000000LL; // 1e18
    vector<u64> a(n);
    for (size_t i = 0; i < n; ++i) {
        long long ai = inf.readLong(0, Bmax, ("a[" + to_string(i) + "]").c_str());
        a[i] = (u64) ai;
    }

    // Read participant's output: accept any whitespace; collect only '0'/'1'
    string bits;
    bits.reserve(n);
    while (!ouf.seekEof()) {
        string tok = ouf.readToken();
        for (char c : tok) {
            if (c == '0' || c == '1') bits.push_back(c);
            else {
                quitf(_wa, "Invalid character '%c' in output (only '0'/'1' allowed).", c);
            }
        }
        if (bits.size() > n) {
            quitf(_wa, "Too many bits: expected %zu, got at least %zu.", n, bits.size());
        }
    }

    if (bits.size() != n) {
        quitf(_wa, "Wrong number of bits: expected %zu, got %zu.", n, bits.size());
    }

    // Compute subset sum with u128
    u128 sum = 0;
    for (size_t i = 0; i < n; ++i) {
        char b = bits[i];
        if (b == '1') sum += (u128)a[i];
        else if (b != '0') quitf(_wa, "Invalid bit at position %zu.", i);
    }

    // error = |sum - T|
    u128 err = (sum >= T) ? (sum - T) : (T - sum);

    // Score ratio in [0, 1]: r = (18 - ln(err + 1)) / 18
    long double err_ld = u128_to_ld(err);
    long double ratio = (18.0L - log1pl(err_ld)) / 18.0L;
    if (ratio < 0.0L) ratio = 0.0L;
    long double unbounded_ratio = ratio;
    if (ratio > 1.0L) ratio = 1.0L;

    long double score100 = ratio * 100.0L;

    // Report partial score with details
    quitp((double)ratio,
          "error=%s, sum=%s, T=%s, score=%.6Lf/100, RatioUnbounded=%.6Lf",
          to_string_u128(err).c_str(),
          to_string_u128(sum).c_str(),
          to_string_u128(T).c_str(),
          score100, unbounded_ratio);
}
