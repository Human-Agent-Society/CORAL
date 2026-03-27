#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int n = inf.readInt(), m = inf.readInt(), s = inf.readInt(), t = inf.readInt();
	println(n, m);

	std::vector<int> u(m), v(m);
	for (int i = 0; i < m; i++) {
		u[i] = inf.readInt(), v[i] = inf.readInt();
		println(u[i], v[i]);
	}

	for (int q = 0; q <= 600; q++) {
		int op = ouf.readInt();
		if (op == 0) {
			std::vector<int> x(m);
			for (int i = 0; i < m; i++) {
				x[i] = ouf.readInt();
				if (x[i] != 0 && x[i] != 1) {
					quitf(_wa, "Invalid query: element %d is out of range [0, 1]", x[i]);
				}
			}

			std::vector<std::vector<int>> adj(n);
			for (int i = 0; i < m; i++) {
				if (x[i] == 0) {
					adj[u[i]].push_back(v[i]);
				} else {
					adj[v[i]].push_back(u[i]);
				}
			}

			std::queue<int> que;
			que.push(s);
			std::vector vis(n, false);
			vis[s] = true;

			while (!que.empty()) {
				int u = que.front();
				que.pop();

				for (int v : adj[u]) {
					if (!vis[v]) {
						vis[v] = true;
						que.push(v);
					}
				}
			}

			println(vis[t]);
		} else if (op == 1) {
			if (ouf.readInt() == s && ouf.readInt() == t) {
				double ratio = 1. * (600 - q) / 600;
				quitp(ratio, "Correct Solution. Ratio: %.4f", ratio);
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