#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int n = inf.readInt(), m = inf.readInt();
	println(m);

	std::vector adj(n, std::vector<int>(m));
	for (int i = 0; i < n; i++) {
		for (int j = 0; j < m; j++) {
			adj[i][j] = inf.readInt();
		}
	}

	std::vector type(n, std::string("center"));
	std::vector pos(n, 0);
	int x = 0, cnt = 0;
	std::vector vis(n, std::vector(m, false));

	for (int q = 0; q <= 50000; q++) {
		if (cnt == n * m) {
			println("treasure");

			double ratio = 1. * (50000 - q) / 50000;
			quitp(ratio, "Ratio: %.4f", ratio);
		}
		println(type[x]);

		int c = ouf.readInt();
		if (c < 0 || c >= m) {
			quitf(_wa, "Invalid query: element %d is out of range [0, %d]", c, m - 1);
		}
		std::string s = ouf.readWord();
		if (s != "left" && s != "right") {
			quitf(_wa, "Invalid query: %s should be left or right.", s.c_str());
		}
		int t = ouf.readInt();
		if (t < 0 || t >= m) {
			quitf(_wa, "Invalid query: element %d is out of range [0, %d]", t, m - 1);
		}

		int y = adj[x][(pos[x] + t) % m];
		if (!vis[x][(pos[x] + t) % m]) {
			vis[x][(pos[x] + t) % m] = true;
			cnt++;
		}
		type[x] = s;
		pos[x] = (pos[x] + c) % m;
		x = y;
	}
	quitp(0., "Too many queries. Ratio: 0.0000");

	return 0;
}