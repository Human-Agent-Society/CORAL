#include "testlib.h"
#include <bits/stdc++.h>

int main(int argc, char* argv[]) {
	registerTestlibCmd(argc, argv);

	double ratio = std::max(1 - 10 * std::abs(ouf.readDouble() / ans.readDouble() - 1), 0.);
	quitp(ratio, "Ratio: %.4f", ratio);

	return 0;
}