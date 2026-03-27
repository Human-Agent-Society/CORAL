#include "testlib.h"
#include <iostream>
#include <map>
#include <algorithm>

using namespace std;

int C[300][300];
int dx[4] = {1, 0, -1, 0}, dy[4] = {0, 1, 0, -1};



int main(int argc, char *argv[]) {
  /*
   * inf: input file
   * ouf: contestant output
   * ans: standard output
   */
  registerTestlibCmd(argc, argv);

  int n = inf.readInt();
  vector<int> inp(n);
  for(int i = 0; i < n; i++){
    inp[i] = inf.readInt() - 1;
  }

  int r = ouf.readInt(0, n);
  int s = ouf.readInt(0, n);
  int p = ouf.readInt(0, n);
  int q = ouf.readInt(0, n);
  vector<int> a(r);
  vector<int> b(s);
  vector<int> c(p);
  vector<int> d(q);

  auto readInts = [&](vector<int> &v){
    for(int i = 0; i < v.size(); i++){
      v[i] = ouf.readInt() - 1;
    }
  };
  readInts(a);
  readInts(b);
  readInts(c);
  readInts(d);
  
// validate if a, b, c, d is a partition of p
  if (a.size() + b.size() + c.size() + d.size() != n) quitf(_wa, "a, b, c, d is not a partition of p");

  vector<int> loc(n), vis(n, 0);
  for (int i = 0; i < n; i++){
    loc[inp[i]] = i;
  }

  for (auto v: {a, b, c, d}){
    for(int i = 0; i < v.size(); i++){
      if(vis[v[i]]) quitf(_wa, "element %d appears twice", v[i]);
      vis[v[i]] = 1;
    }
    for (int i = 0; i + 1 < v.size(); i++){
      if(loc[v[i]] > loc[v[i + 1]]) quitf(_wa, "the order of elements in %d is wrong", v[i]);
    }
  }

  // calculate score by LIS and LDS
  auto calc_lis = [&](vector<int> v, bool rev){
    if (rev) reverse(v.begin(), v.end());
    const int INF = 1e9;
    vector<int> dp(v.size() + 1, INF);
    for(int i = 0; i < v.size(); i++){
      int pos = lower_bound(dp.begin(), dp.end(), v[i]) - dp.begin();
      dp[pos] = v[i];
    }
    return lower_bound(dp.begin(), dp.end(), INF) - dp.begin();
  };
  int lis_a = calc_lis(a, false);
  int lds_b = calc_lis(b, true);
  int lis_c = calc_lis(c, false);
  int lds_d = calc_lis(d, true);
  int score = lis_a + lds_b + lis_c + lds_d;

  double score_ratio = (double)score / (double)n;
  // printf("score: %d, score_ratio: %.4f\n", score, score_ratio);
  // cerr << "score: " << score << ", score_ratio: " << score_ratio << endl;
  // quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, score_ratio);
  quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", score, score_ratio, score_ratio);

}