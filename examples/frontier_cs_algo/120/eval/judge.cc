#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char ** argv){
	registerInteraction(argc, argv);

	std::array<std::string, 100> adj;
	for (int i = 0; i < 100; i++) {
		adj[i] = inf.readWord();
	}

	for (int q = 0; q <= 161700; q++) {
		std::string op = ouf.readToken();
		if (op == "?") {
			int a = ouf.readInt();
			if (a < 1 || a > 100) {
				quitf(_wa, "Invalid query: element %d is out of range [1, 100]", a);
			}
			a--;
			int b = ouf.readInt();
			if (b < 1 || b > 100) {
				quitf(_wa, "Invalid query: element %d is out of range [1, 100]", b);
			}
			b--;
			if (b == a) {
				quitf(_wa, "Vertices need to be pairwise different.");
			}
			int c = ouf.readInt();
			if (c < 1 || c > 100) {
				quitf(_wa, "Invalid query: element %d is out of range [1, 100]", c);
			}
			c--;
			if (c == a || c == b) {
				quitf(_wa, "Vertices need to be pairwise different.");
			}

			println((adj[a][b] == '1') + (adj[a][c] == '1') + (adj[b][c] == '1'));
		} else if (op == "!") {
			std::array<std::string, 100> guess;
			for (int i = 0; i < 100; i++) {
				guess[i] = ouf.readWord();
			}
			if (guess == adj) {
				double ratio_unbounded = 3400.0 / (q + 1);
				double ratio = std::min(1.0, ratio_unbounded);
				quitp(ratio, "Correct guess. Ratio: %.4f, RatioUnbounded: %.4f", ratio, ratio_unbounded);
			} else {
				quitp(0., "Wrong guess. Ratio: 0.0000");
			}
		}
	}
	quitp(0., "Too many queries. Ratio: 0.0000");

	return 0;
}