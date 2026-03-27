#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerTestlibCmd(argc, argv);

	int n = inf.readInt(), m = inf.readInt();

	std::vector<std::vector<int>> a(n + 1);
	for (int i = 0; i < n; i++) {
		a[i].resize(m);
		for (int j = 0; j < m; j++) {
			a[i][j] = inf.readInt();
			a[i][j]--;
		}
	}

	int k = ouf.readInt();
	if (k < 0 || k > int(1e7)) {
		quitf(_wa, "Invalid: element %d is out of range [1, 10000000]", k);
	}
	for (int t = 0; t < k; t++) {
		int i = ouf.readInt();
		if (i < 1 || i > n + 1) {
			quitf(_wa, "Invalid: element %d is out of range [1, %d]", i, n + 1);
		}
		int j = ouf.readInt();
		if (j < 1 || j > n + 1) {
			quitf(_wa, "Invalid: element %d is out of range [1, %d]", j, n + 1);
		}
		if (i == j) {
			quitf(_wa, "Invalid: elemet %d and %d cannot be equal.", i, j);
		}
		i--, j--;

		if (a[i].empty()) {
			quitf(_wa, "Invalid: stack %d is empty.", i + 1);
		} else if (int(a[j].size()) == m) {
			quitf(_wa, "Invalid: stack %d is full.", j + 1);
		} else {
			a[j].push_back(a[i].back());
			a[i].pop_back();
		}
	}

	for (int i = 0; i < n; i++) {
		if (a[i].empty() || a[i] != std::vector(m, a[i][0])) {
			quitp(0., "Incorrect Solution. Ratio: 0.0000");
		}
	}
	if (!a[n].empty()) {
		quitp(0., "Incorrect Solution. Ratio: 0.0000");
	}

	double ratio = 1. * (1e7 - k) / 1e7;
	quitp(ratio, "Correct Solution. Ratio: %.4f", ratio);

	return 0;
}