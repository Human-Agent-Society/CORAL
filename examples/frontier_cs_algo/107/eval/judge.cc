#include "testlib.h"
#include <bits/stdc++.h>

using i64 = long long;

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int t = inf.readInt();
	println(t);

	int max = 0;
	while (t--) {
		int x = inf.readInt();
		for (int q = 0; q <= 100; q++) {
			if (q == 100) {
				quitp(0., "Too many queries. Ratio: 0.0000");
			}

			int op = ouf.readInt();
			if (op == 0) {
				i64 y = ouf.readLong();
				if (y < 1 || y > 1000000000000000000) {
					quitf(_wa, "Invalid query: element %d is out of range [1, 1000000000000000000]", y);
				}

				println(std::gcd(x, y));
			} else if (op == 1) {
				int a = ans.readInt(), d = ouf.readInt();
				if (std::abs(a - d) <= 7 || (2 * a >= d && 2 * d >= a)) {
					max = std::max(max, q);
					break;
				} else {
					quitp(0., "Wrong guess. Ratio: 0.0000");
				}
			} else {
				quitf(_wa, "Invalid action type: expected 0 or 1, but got %d", op);
			}
		}
	}

	double ratio = 1. * (100 - max) / 100;
	quitp(ratio, "Ratio: %.4f", ratio);

	return 0;
}