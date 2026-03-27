#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char ** argv){
	registerInteraction(argc, argv);

	int n = inf.readInt();
	println(n);

	std::vector<int> o(n);
	for (int i = 0; i < n; i++) {
		o[i] = inf.readInt();
	}

	for (int q = 0; q <= 600; q++) {
		std::string op = ouf.readToken();
		if (op == "?") {
			int res = ouf.readInt();
			if (res < 0 || res >= 1000000007) {
				quitf(_wa, "Invalid query: element %d is out of range [1, 1000000006]", res);
			}

			for (int i = 0; i < n; i++) {
				int x = ouf.readInt();
				if (x < 0 || x >= 1000000007) {
					quitf(_wa, "Invalid query: element %d is out of range [1, 1000000006]", x);
				}

				res = (o[i] == 0 ? (res + x) % 1000000007 : 1ll * res * x % 1000000007);
			}

			println(res);
		} else if (op == "!") {
			std::vector<int> guess(n);
			for (int i = 0; i < n; i++) {
				guess[i] = ouf.readInt();
			}

			if (guess == o) {
				double ratio_unbounded = (40.0 + 1) / (q + 1);
				double ratio = std::min(1.0, ratio_unbounded);
				quitp(ratio, "Correct guess. Ratio: %.4f, RatioUnbounded: %.4f", ratio, ratio_unbounded);
			} else {
				quitp(0., "Wrong guess. Ratio: 0.0000");
			}
		} else {
			quitf(_wa, "Invalid action type: expected ? or !, but got %s", op.c_str());
		}
	}
	quitp(0., "Too many queries. Ratio: 0.0000");

	return 0;
}