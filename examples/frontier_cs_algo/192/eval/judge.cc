#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(1, 1000);
  int m = inf.readInt(0, 20000);

  vector<pair<int,int>> edges(m);
  for (int i = 0; i < m; i++) {
    int u = inf.readInt(1, n);
    int v = inf.readInt(1, n);
    if (u == v) {
      quitf(_wa, "self-loop on node %d", u);
    }
    edges[i] = {u - 1, v - 1};
  }

  vector<int> side(n);
  for (int i = 0; i < n; i++) {
    side[i] = ouf.readInt(0, 1);
  }

  int cut = 0;
  for (auto &[u, v] : edges) {
    if (side[u] != side[v]) cut++;
  }

  double ratio;
  if (m == 0) {
    ratio = 1.0;
  } else {
    ratio = (double)cut / (double)m;
  }

  ratio = max(0.0, min(1.0, ratio));
  quitp(ratio, "Ratio: %.6f", ratio);
}
