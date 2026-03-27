#include "testlib.h"
#include <vector>
#include <cassert>
#include <cmath>

using namespace std;

const double p1 = 0.0001, p2 = 0.001, p3 = 0.01, p4 = 0.1;

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    double answ = ans.readDouble();
    double ans_guess = ouf.readDouble();
    double diff = fabs(ans_guess - answ);

    // Smooth continuous scoring (0 ~ 100), only p2 is used
    double score = 100.0 / (1.0 + diff / (p1 * p3));

    double score_ratio = score / 100.0;
    double unbounded_ratio = score_ratio;
    score_ratio = min(score_ratio, 1.0);

    quitp(score_ratio,
          "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f, diff = %.10f",
          (long long)score, score_ratio, unbounded_ratio, diff);
}
