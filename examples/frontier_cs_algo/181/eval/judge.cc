#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(2, 2000);

  vector<vector<int>> D(n + 1, vector<int>(n + 1));
  vector<vector<int>> F(n + 1, vector<int>(n + 1));

  // Read distance matrix D
  for (int i = 1; i <= n; i++) {
    for (int j = 1; j <= n; j++) {
      D[i][j] = inf.readInt(0, 1);
    }
  }

  // Read flow matrix F
  for (int i = 1; i <= n; i++) {
    for (int j = 1; j <= n; j++) {
      F[i][j] = inf.readInt(0, 1);
    }
  }

  // Read permutation p: facility -> location
  vector<int> p(n + 1), used(n + 1, 0);
  for (int i = 1; i <= n; i++) {
    p[i] = ouf.readInt(1, n);
    if (used[p[i]]) {
      quitf(_wa, "not a permutation");
    }
    used[p[i]] = 1;
  }

  long long cost = 0;
  long long totalFlow = 0;

  for (int i = 1; i <= n; i++) {
    for (int j = 1; j <= n; j++) {
      if (F[i][j]) {
        totalFlow++;
        cost += D[p[i]][p[j]];
      }
    }
  }

  double score = 0.0;
  if (totalFlow > 0) {
    score = (double) cost / (double) totalFlow;
  }

  score = max(0.0, min(1.0, 1 - score));

  // EXACT same output format as previous checker
  quitp(score, "Ratio: %.6f", score);
}