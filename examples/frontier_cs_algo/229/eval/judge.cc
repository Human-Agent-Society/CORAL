#include "testlib.h"
#include <iostream>
#include <map>
#include <algorithm>

using namespace std;
typedef long long ll;
int C[300][300];
int dx[4] = {1, 0, -1, 0}, dy[4] = {0, 1, 0, -1};



int main(int argc, char *argv[]) {
  /*
   * inf: input file
   * ouf: contestant output
   * ans: standard output
   */
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(), x = inf.readInt();
  vector<long long> inp(n);
  for(int i = 0; i < n; i++){
    inp[i] = inf.readInt(1, (ll)1e9);
  }

  int res = ouf.readInt();
  for(int i = 0; i < 10; i++){
    int l = ouf.readInt(1, n);
    int r = ouf.readInt(l, n);
    int d = ouf.readInt();
    l--, r--;
    for(int j = l; j <= r; j++){
      inp[j] += d;
    }
  }
  auto calc_lis = [&](vector<ll> v){
    const ll INF = (ll)1e18;
    vector<ll> dp(v.size() + 1, INF);
    for(int i = 0; i < v.size(); i++){
      int pos = lower_bound(dp.begin(), dp.end(), v[i]) - dp.begin();
      dp[pos] = v[i];
    }
    return lower_bound(dp.begin(), dp.end(), INF) - dp.begin();
  };

  int real_lis = calc_lis(inp);
  
  if (real_lis != res) quitf(_wa, "wrong answer");

  double score_ratio = (double)res / (double)n;
  quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", res, score_ratio, score_ratio);

}