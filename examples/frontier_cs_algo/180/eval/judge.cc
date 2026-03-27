#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(2, 2000);
  int m = inf.readInt(1, n * (n - 1) / 2);

  // Read G1 edges
  set<pair<int,int>> E1;
  for (int i = 0; i < m; i++) {
    int u = inf.readInt(1, n);
    int v = inf.readInt(1, n);
    if (u == v) quitf(_wa, "self-loop in G1");
    if (u > v) swap(u, v);
    E1.insert({u, v});
  }

  // Read G2 edges
  vector<pair<int,int>> E2(m);
  for (int i = 0; i < m; i++) {
    int u = inf.readInt(1, n);
    int v = inf.readInt(1, n);
    if (u == v) quitf(_wa, "self-loop in G2");
    if (u > v) swap(u, v);
    E2[i] = {u, v};
  }

  // Read permutation p (G2 -> G1)
  vector<int> p(n + 1), used(n + 1, 0);
  for (int i = 1; i <= n; i++) {
    p[i] = ouf.readInt(1, n);
    if (used[p[i]]) {
      quitf(_wa, "not a permutation");
    }
    used[p[i]] = 1;
  }

  // Count matched edges
  int matched = 0;
  for (auto &e : E2) {
    int u = p[e.first];
    int v = p[e.second];
    if (u > v) swap(u, v);
    if (E1.count({u, v})) {
      matched++;
    }
  }

  double score = 0.0;
  if (m > 0) score = (double)matched / m;
  score = max(0.0, min(1.0, score));

  // EXACT same output format as old checker
  quitp(score, "Ratio: %.6f", score);
}
