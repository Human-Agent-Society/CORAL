#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int t = inf.readInt();
	println(t);

	int cnt = 0;
	for (int tt = 0; tt < t; tt++) {
		int n = inf.readInt();
		println(n);

		std::vector<int> a(n);
		for (int i = 0; i < n; i++) {
			a[i] = inf.readInt();
		}

		while (true) {
			int op = ouf.readInt();
			if (op == 0) {
				int i = ouf.readInt();
				if (i < 0 || i >= n) {
					quitf(_wa, "Invalid query: element %d is out of range [0, %d]", i, n - 1);
				}

				if (a[i]) {
					a[i]--;
					println(1);
				} else {
					println(0);
				}
			} else if (op == 1) {
				int i = ouf.readInt();
				if (i < 0 || i >= n) {
					quitf(_wa, "Invalid query: element %d is out of range [0, %d]", i, n - 1);
				}
				int j = ouf.readInt();
				if (j < 0 || j >= n) {
					quitf(_wa, "Invalid query: element %d is out of range [0, %d]", j, n - 1);
				}
				if (i == j) {
					quitf(_wa, "%d and %d can not be equal.", i, j);
				}

				cnt += a[i] + a[j] >= n;
				break;
			} else {
				quitf(_wa, "Invalid action type: expected 0 or 1, but got %d", op);
			}
		}
	}

	double ratio = 1. * cnt / t;
	quitp(ratio, "Ratio: %.4f", ratio);

	return 0;
}