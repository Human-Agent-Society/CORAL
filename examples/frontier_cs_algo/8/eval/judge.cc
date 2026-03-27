#include "testlib.h"
#include <bits/stdc++.h>

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

constexpr int P = 998244353;

int main(int argc, char* argv[]) {
	registerTestlibCmd(argc, argv);

	int n = ouf.readInt();
	if (n < 0 || n > 512) {
		quitf(_wa, "Invalid: element %d is out of range [0, 512]", n);
	}

	std::vector<std::vector<int>> a(n);
	for (int i = 0; i < n; i++) {
		auto s = ouf.readWord();
		if (s == "POP") {
			a[i].resize(4);
			a[i][0] = ouf.readInt();
			if (a[i][0] < 1 || a[i][0] > 1024) {
				quitf(_wa, "Invalid: element %d is out of range [1, 1024]", a[i][0]);
			}
			if (ouf.readWord() != "GOTO") {
				quitf(_wa, "Invalid format.");
			}
			a[i][1] = ouf.readInt();
			if (a[i][1] < 1 || a[i][1] > n) {
				quitf(_wa, "Invalid: element %d is out of range [1, %d]", a[i][1], n);
			}
			a[i][1]--;
			if (ouf.readWord() != "PUSH") {
				quitf(_wa, "Invalid format.");
			}
			a[i][2] = ouf.readInt();
			if (a[i][2] < 1 || a[i][2] > 1024) {
				quitf(_wa, "Invalid: element %d is out of range [1, 1024]", a[i][2]);
			}
			if (ouf.readWord() != "GOTO") {
				quitf(_wa, "Invalid format.");
			}
			a[i][3] = ouf.readInt();
			if (a[i][3] < 1 || a[i][3] > n) {
				quitf(_wa, "Invalid: element %d is out of range [1, %d]", a[i][3], n);
			}
			a[i][3]--;
		} else if (s == "HALT") {
			a[i].resize(2);
			if (ouf.readWord() != "PUSH") {
				quitf(_wa, "Invalid format.");
			}
			a[i][0] = ouf.readInt();
			if (a[i][0] < 1 || a[i][0] > 1024) {
				quitf(_wa, "Invalid: element %d is out of range [1, 1024]", a[i][0]);
			}
			if (ouf.readWord() != "GOTO") {
				quitf(_wa, "Invalid format.");
			}
			a[i][1] = ouf.readInt();
			if (a[i][1] < 1 || a[i][1] > n) {
				quitf(_wa, "Invalid: element %d is out of range [1, %d]", a[i][1], n);
			}
			a[i][1]--;
		} else {
			quitf(_wa, "Invalid format.");
		}
	}

	std::vector<std::array<std::optional<std::pair<int, MInt<P>>>, 1025>> dp(n);
	std::vector vis(n, std::array<bool, 1025>{});

	auto solve = [&](auto &&self, int i, int x) -> std::pair<int, MInt<P>> {
		if (dp[i][x]) {
			return dp[i][x].value();
		}
		if (vis[i][x]) {
			quitf(_wa, "The program never halts.");
		}

		vis[i][x] = true;
		if (a[i].size() == 4) {
			if (x == a[i][0]) {
				dp[i][x] = {a[i][1], 1};
			} else {
				auto [j, u] = self(self, a[i][3], a[i][2]);
				auto [k, v] = self(self, j, x);

				dp[i][x] = {k, u + v + 1};
			}
		} else {
			if (x == 0) {
				dp[i][x] = {-1, 1};
			} else {
				auto [j, u] = self(self, a[i][1], a[i][0]);
				auto [k, v] = self(self, j, x);

				dp[i][x] = {k, u + v + 1};
			}
		}
		return dp[i][x].value();
	};

	if (solve(solve, 0, 0).second == MInt<P>(inf.readInt())) {
		double ratio = 1. * (512 - n) / 512;
		quitp(ratio, "Correct Solution. Ratio: %.4f", ratio);
	} else {
		quitf(_wa, "Incorrect Solution.");
	}

	return 0;
}