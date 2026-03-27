#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char ** argv){
	registerInteraction(argc, argv);
    std::cout.setf(std::ios::fixed);
    std::cout.precision(20);

	int n = inf.readInt();
	println(n);

	std::vector<int> a(n);
	for (int i = 0; i < n; i++) {
		a[i] = inf.readInt();
	}
	std::vector<int> b(n);
	for (int i = 0; i < n; i++) {
		b[i] = inf.readInt();
	}

	for (int q = 0; q <= 10000; q++) {
		std::string op = ouf.readToken();
		if (op == "?") {
			long double x = ouf.readDouble();
			if (!std::isfinite(x) || x < -1e12 || x > 1e12) {
				quitf(_wa, "Invalid query: element %.4f is out of range [-1000000000000, 1000000000000]", x);
			}
			long double y = ouf.readDouble();
			if (!std::isfinite(y) || y < -1e12 || y > 1e12) {
				quitf(_wa, "Invalid query: element %.4f is out of range [-1000000000000, 1000000000000]", y);
			}

			long double sum = 0;
			for (int i = 0; i < n; i++) {
				sum += std::abs(a[i] * x - y + b[i]) / std::sqrt(a[i] * a[i] + 1);
			}

			std::cout << sum << std::endl;
		} else if (op == "!") {
			std::vector<int> ga(n);
			for (int i = 0; i < n; i++) {
				ga[i] = ouf.readInt();
			}
			std::vector<int> gb(n);
			for (int i = 0; i < n; i++) {
				gb[i] = ouf.readInt();
			}

			std::vector<int> o(n);
			std::iota(o.begin(), o.end(), 0);
			std::sort(o.begin(), o.end(), [&](int i, int j) -> bool {
				return std::pair{ga[i], gb[i]} < std::pair{ga[j], gb[j]};
			});

			for (int i = 0; i < n; i++) {
				if (ga[o[i]] != a[i] || gb[o[i]] != b[i]) {
					quitp(0., "Wrong guess. Ratio: 0.0000");
				}
			}

			double ratio = q <= 402 ? 1 : 1 - .7 * (q - 402) / (10000 - 402);
			double unbounded_ratio = 1 - .7 * (q - 402) / (10000 - 402);
			if (ratio < 0) ratio = 0.0;
			quitp(ratio, "Correct guess. Ratio: %.4f, RatioUnbounded: %.4f", ratio, unbounded_ratio);
		} else {
			quitf(_wa, "Invalid action type: expected ? or !, but got %s", op.c_str());
		}
	}
	quitp(0., "Too many queries. Ratio: 0.0000");

	return 0;
}