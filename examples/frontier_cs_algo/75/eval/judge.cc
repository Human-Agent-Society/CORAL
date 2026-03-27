#include "testlib.h"
#include <bits/stdc++.h>

struct DSU {
	std::vector<int> f, siz;

	DSU() {}
	DSU(int n) {
		init(n);
	}

	void init(int n) {
		f.resize(n);
		std::iota(f.begin(), f.end(), 0);
		siz.assign(n, 1);
	}

	int find(int x) {
		while (x != f[x]) {
			x = f[x] = f[f[x]];
		}
		return x;
	}

	bool same(int x, int y) {
		return find(x) == find(y);
	}

	bool merge(int x, int y) {
		x = find(x), y = find(y);
		if (x == y) {
			return false;
		}
		f[y] = x;
		siz[x] += siz[y];
		return true;
	}

	int size(int x) {
		return siz[find(x)];
	}
};

int main(int argc, char* argv[]) {
	registerTestlibCmd(argc, argv);

	int b = inf.readInt(), w = inf.readInt(), x = inf.readInt(), y = inf.readInt();

	int n = ouf.readInt();
	if (n < 1 || n > 100000) {
		quitf(_wa, "Invalid: element %d is out of range [1, 100000]", n);
	}
	int m = ouf.readInt();
	if (m < 1 || m > 100000) {
		quitf(_wa, "Invalid: element %d is out of range [1, 100000]", m);
	}
	if (n * m >= 100000) {
		quitf(_wa, "Invalid: grid is too big.");
	}

	std::vector<std::string> s(n);
	for (int i = 0; i < n; i++) {
		s[i] = ouf.readWord();
		if (int(s[i].length()) != m || std::count(s[i].begin(), s[i].end(), '@') + std::count(s[i].begin(), s[i].end(), '.') != m) {
			quitf(_wa, "Invalid: wrong format.");
		}
	}

	DSU dsu(n * m);
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < m; j++) {
			if (i + 1 < n && s[i][j] == s[i + 1][j]) {
				dsu.merge(i * m + j, (i + 1) * m + j);
			}
			if (j + 1 < m && s[i][j] == s[i][j + 1]) {
				dsu.merge(i * m + j, i * m + j + 1);
			}
		}
	}

	for (int i = 0; i < n; i++) {
		for (int j = 0; j < m; j++) {
			(s[i][j] == '@' ? b : w) -= dsu.find(i * m + j) == i * m + j;
		}
	}
	if (b || w) {
		quitp(0., "Incorrect Solution. Ratio: 0.0000");
	}

	int sum = 0;
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < m; j++) {
			sum += s[i][j] == '@' ? x : y;
		}
	}

	double ratio = std::max(1. * (8000 * (x + y) - sum) / (8000 * (x + y)), 0.);
	quitp(ratio, "Correct Solution. Ratio: %.4f", ratio);

	return 0;
}