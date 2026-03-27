#include "testlib.h"
#include <bits/stdc++.h>

using i64 = long long;

int main(int argc, char* argv[]) {
	registerInteraction(argc, argv);

	int n = inf.readInt();

	int max = 1e6, tot = 0;
	std::vector cnt(n, 0);

	while (true) {
		int action_type = ouf.readInt();
		if (action_type == 0) {
			int m = ouf.readInt();
			tot += m;
			if (tot > max) {
				quitp(0., "Total size limit exceeded. Max total size: %d. Ratio: 0.0000", max);
			}

			std::vector<i64> a(m);
			for (int i = 0; i < m; i++) {
				a[i] = ouf.readLong();
				if (a[i] < 1 || a[i] > i64(1e18)) {
					quitf(_wa, "Invalid query: element %lld is out of range [%d, %lld]", a[i], 1, i64(1e18));
				}
			}

			i64 collisions = 0;
			for (int i = 0; i < m; i++) {
				collisions += cnt[a[i] % n]++;
			}
			for (int i = 0; i < m; i++) {
				cnt[a[i] % n]--;
			}
			println(collisions);
		} else if (action_type == 1) {
			if (ouf.readInt() == n) {
				double ratio_unbounded = (1000000.0 + 1) / (tot + 1);
				double ratio = std::min(1.0, ratio_unbounded);

				quitp(ratio, "Correct guess in %d queries. Ratio: %.4f, RatioUnbounded: %.4f", tot, ratio, ratio_unbounded);
			} else {
				quitp(0., "Wrong guess. Ratio: 0.0000");
			}
			break;
		} else {
			quitf(_wa, "Invalid action type: expected 0 or 1, but got %d", action_type);
		}
	}

	return 0;
}