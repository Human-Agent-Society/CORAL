#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

/* minimal non-negative big integer, base 10 */
struct BigInt {
  vector<int> d; // reversed digits

  BigInt() {}
  BigInt(const string &s) { fromString(s); }

  void fromString(const string &s) {
    d.clear();
    for (int i = (int)s.size() - 1; i >= 0; --i) {
      if (isdigit(s[i])) d.push_back(s[i] - '0');
    }
    trim();
  }

  void trim() {
    while (!d.empty() && d.back() == 0) d.pop_back();
  }

  bool isZero() const { return d.empty(); }

  static int cmp(const BigInt &a, const BigInt &b) {
    if (a.d.size() != b.d.size())
      return a.d.size() < b.d.size() ? -1 : 1;
    for (int i = (int)a.d.size() - 1; i >= 0; --i) {
      if (a.d[i] != b.d[i])
        return a.d[i] < b.d[i] ? -1 : 1;
    }
    return 0;
  }

  static BigInt add(const BigInt &a, const BigInt &b) {
    BigInt c;
    int n = max(a.d.size(), b.d.size());
    c.d.resize(n);
    int carry = 0;
    for (int i = 0; i < n; ++i) {
      int x = carry;
      if (i < (int)a.d.size()) x += a.d[i];
      if (i < (int)b.d.size()) x += b.d[i];
      c.d[i] = x % 10;
      carry = x / 10;
    }
    if (carry) c.d.push_back(carry);
    return c;
  }

  // assume a >= b
  static BigInt sub(const BigInt &a, const BigInt &b) {
    BigInt c;
    c.d.resize(a.d.size());
    int borrow = 0;
    for (int i = 0; i < (int)a.d.size(); ++i) {
      int x = a.d[i] - borrow - (i < (int)b.d.size() ? b.d[i] : 0);
      if (x < 0) {
        x += 10;
        borrow = 1;
      } else {
        borrow = 0;
      }
      c.d[i] = x;
    }
    c.trim();
    return c;
  }

  // compute a / b as long double, b > 0, a <= b * something small
  static long double divToLongDouble(const BigInt &a, const BigInt &b) {
    // long division, only fractional part needed
    BigInt cur;
    long double res = 0.0L;
    long double place = 1.0L;

    BigInt rem = a;

    for (int iter = 0; iter < 25; ++iter) { // ~18 digits precision
      // rem *= 10
      BigInt tmp;
      tmp.d.assign(rem.d.size() + 1, 0);
      for (int i = 0; i < (int)rem.d.size(); ++i)
        tmp.d[i + 1] = rem.d[i];
      rem = tmp;
      rem.trim();

      int digit = 0;
      while (cmp(rem, b) >= 0) {
        rem = sub(rem, b);
        digit++;
      }
      place /= 10.0L;
      res += digit * place;
    }
    return res;
  }

  string toString() const {
    if (isZero()) {
      return "0";
    }
    string s;
    for (int i = (int)d.size() - 1; i >= 0; --i) {
      s.push_back(char('0' + d[i]));
    }
    return s;
  }
};

int main(int argc, char* argv[]) {
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(1, 2100);
  BigInt W(inf.readToken());

  vector<BigInt> a(n);
  BigInt M; // max element
  string input;
  for (int i = 0; i < n; ++i) {
    a[i] = BigInt(inf.readToken());
    if (BigInt::cmp(a[i], M) > 0) M = a[i];
  }

  BigInt S; // selected sum
  for (int i = 0; i < n; ++i) {
    int b = ouf.readInt(0, 1);
    if (b == 1) {
      S = BigInt::add(S, a[i]);
    }
  }

  BigInt diff;
  if (BigInt::cmp(W, S) >= 0) diff = BigInt::sub(W, S);
  else diff = BigInt::sub(S, W);

  BigInt denom = BigInt::add(W, M);

  double ratio;
  if (denom.isZero()) {
    ratio = 0.0;
  } else {
    BigInt num = BigInt::sub(denom, diff); // (W + M) - |W - S|
    long double r = BigInt::divToLongDouble(num, denom);
    ratio = (double)r;
  }

  ratio = max(0.0, min(1.0, ratio));

  quitp(ratio,
        "Ratio: %.6f", ratio);
}
