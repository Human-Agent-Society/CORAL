#include "testlib.h"
#include <bits/stdc++.h>

using i64 = long long;

template<int P = 0>
struct MInt {
	static int m;
	static constexpr int mod() {
		return P ? P : m;
	}
	static constexpr void set(int m) {
		MInt::m = m;
	}

	int x;

	constexpr MInt(): x(0) {}
	template<class T>
	constexpr MInt(const T &x): x(int(x % mod() + mod()) % mod()) {}

	template<class T>
	explicit constexpr operator T() const {
		return T(x);
	}

	template<class T>
	constexpr MInt pow(T b) const {
		MInt res = 1;
		for (MInt a = *this; b; a *= a, b >>= 1) {
			if (b & 1) {
				res *= a;
			}
		}
		return res;
	}

	constexpr MInt inv() const {
		assert(x);
		return pow(mod() - 2);
	}

	constexpr MInt &operator+=(const MInt &b) {
		x += b.x;
		if (x >= mod()) {
			x -= mod();
		}
		return *this;
	}
	constexpr MInt &operator-=(const MInt &b) {
		x -= b.x;
		if (x < 0) {
			x += mod();
		}
		return *this;
	}
	constexpr MInt &operator*=(const MInt &b) {
		x = 1ll * x * b.x % mod();
		return *this;
	}
	constexpr MInt &operator/=(const MInt &b) {
		return *this = *this * b.inv();
	}

	friend constexpr MInt operator+(const MInt &a, const MInt &b) {
		return MInt(a) += b;
	}
	friend constexpr MInt operator-(const MInt &a, const MInt &b) {
		return MInt(a) -= b;
	}
	friend constexpr MInt operator*(const MInt &a, const MInt &b) {
		return MInt(a) *= b;
	}
	friend constexpr MInt operator/(const MInt &a, const MInt &b) {
		return MInt(a) /= b;
	}

	constexpr MInt &operator++() {
		return *this += 1;
	}
	constexpr MInt &operator--() {
		return *this -= 1;
	}

	constexpr MInt operator++(int) {
		MInt res = *this;
		++*this;
		return res;
	}
	constexpr MInt operator--(int) {
		MInt res = *this;
		--*this;
		return res;
	}

	constexpr MInt operator+() const {
		return *this;
	}
	constexpr MInt operator-() const {
		return 0 - *this;
	}

	friend constexpr bool operator==(const MInt &a, const MInt &b) {
		return int(a) == int(b);
	}
	friend constexpr bool operator!=(const MInt &a, const MInt &b) {
		return int(a) != int(b);
	}

	friend constexpr std::istream &operator>>(std::istream &is, MInt &a) {
		int v;
		is >> v;
		a = v;
		return is;
	}
	friend constexpr std::ostream &operator<<(std::ostream &os, const MInt &a) {
		return os << int(a);
	}
};

template<int P>
int MInt<P>::m = 1;

template<int x, int P>
constexpr MInt<P> cinv = MInt<P>(x).inv();

constexpr int P0 = 998244353, P1 = 1e9 + 7;

int main(int argc, char* argv[]) {
	registerTestlibCmd(argc, argv);

	int n = ouf.readInt();
	if (n < 1 || n > 300) {
		quitf(_wa, "Invalid: element %d is out of range [1, 300]", n);
	}

	std::vector a(n, std::vector<int>(n));
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < n; j++) {
			a[i][j] = ouf.readInt();
			if (a[i][j] != 0 && a[i][j] != 1) {
				quitf(_wa, "Invalid: element %d is out of range [0, 1]", a[i][j]);
			}
		}
	}

	std::vector dp0(n, std::vector(n, MInt<P0>(0)));
	dp0[0][0] = a[0][0];
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < n; j++) {
			if (i + 1 < n && a[i + 1][j]) {
				dp0[i + 1][j] += dp0[i][j];
			}
			if (j + 1 < n && a[i][j + 1]) {
				dp0[i][j + 1] += dp0[i][j];
			}
		}
	}
	std::vector dp1(n, std::vector(n, MInt<P1>(0)));
	dp1[0][0] = a[0][0];
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < n; j++) {
			if (i + 1 < n && a[i + 1][j]) {
				dp1[i + 1][j] += dp1[i][j];
			}
			if (j + 1 < n && a[i][j + 1]) {
				dp1[i][j + 1] += dp1[i][j];
			}
		}
	}

	i64 x = inf.readLong();
	if (dp0[n - 1][n - 1] == MInt<P0>(x) && dp1[n - 1][n - 1] == MInt<P1>(x)) {
		double ratio = 1. * (300 - n) / 300;
		quitp(ratio, "Correct solution. Ratio: %.4f", ratio);
	} else {
		quitp(0., "Incorrect solution. Ratio: 0.0000");
	}

	return 0;
}