#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(1, 3000);
  int m = inf.readInt(0, 2000000);

  vector<array<int,3>> clauses(m);
  for (int i = 0; i < m; i++) {
    int a = inf.readInt(-n, n);
    int b = inf.readInt(-n, n);
    int c = inf.readInt(-n, n);
    if (a == 0 || b == 0 || c == 0) {
      quitf(_wa, "literal cannot be zero");
    }
    clauses[i] = {a, b, c};
  }

  vector<int> val(n + 1);
  for (int i = 1; i <= n; i++) {
    val[i] = ouf.readInt(0, 1);
  }

  int sat = 0;
  for (auto &cl : clauses) {
    bool ok = false;
    for (int k = 0; k < 3; k++) {
      int x = cl[k];
      int v = abs(x);
      bool lit = (x > 0 ? val[v] == 1 : val[v] == 0);
      if (lit) {
        ok = true;
        break;
      }
    }
    if (ok) sat++;
  }

  double score = 1.0;
  if (m > 0) score = (double)sat / m;
  score = max(0.0, min(1.0, score));

  quitp(score, "Ratio: %.6f", score);
}
