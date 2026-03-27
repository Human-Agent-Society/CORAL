#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int n = inf.readInt();
	println(n);

	std::vector<int> a(n);
	for (int i = 0; i < n; i++) {
		a[i] = inf.readInt();
	}

	std::vector s(n + 1, std::vector(n + 1, false));
	for (int i = 0; i < n; i++) {
		for (int j = i + 1; j < n; j++) {
			s[i + 1][j + 1] = a[i] > a[j];
		}
	}
	for (int i = 0; i < n; i++) {
		for (int j = 0; j <= n; j++) {
			s[i + 1][j] = s[i + 1][j] ^ s[i][j];
		}
	}
	for (int i = 0; i <= n; i++) {
		for (int j = 0; j < n; j++) {
			s[i][j + 1] = s[i][j + 1] ^ s[i][j];
		}
	}

	for (int q = 0; q <= 1999000; q++) {
		int op = ouf.readInt();
		if (op == 0) {
			int l = ouf.readInt();
			if (l < 1 || l > n) {
				quitf(_wa, "Invalid query: element %d is out of range [1, %d]", l, n);
			}
			int r = ouf.readInt();
			if (r < 1 || r > n) {
				quitf(_wa, "Invalid query: element %d is out of range [1, %d]", r, n);
			}
			if (l > r) {
				quitf(_wa, "Invalid query: not an interval.");
			}
			l--;

			println(s[r][r] ^ s[l][r] ^ s[r][l] ^ s[l][l]);
		} else if (op == 1) {
			std::vector<int> b(n);
			for (int i = 0; i < n; i++) {
				b[i] = ouf.readInt();
			}
			if (b == a) {
				double ratio = (std::exp(1. * -q / 249875) - std::exp(-8)) / (1 - std::exp(-8));
				quitp(ratio, "Correct guess. Ratio: %.4f", ratio);
			} else {
				quitp(0., "Wrong guess. Ratio: 0.0000");
			}
		} else {
			quitf(_wa, "Invalid action type: expected 0 or 1, but got %d", op);
		}
	}
	quitp(0., "Too many queries. Ratio: 0.0000");

	return 0;
}