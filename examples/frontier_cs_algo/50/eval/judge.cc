#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;

int cost[5010];

vector<int>v[5010];

int vis[1010];

int main(int argc, char *argv[]) {
  /*
   * inf：输入
   * ouf：选手输出
   * ans：标准输出
   */
  registerTestlibCmd(argc, argv);

  int n = inf.readInt(1, 400), m = inf.readInt(1, 4000);
  for(int i = 1; i <= m; i++){
    cost[i] = inf.readInt();
  }
  for(int i = 1; i <= n; i++){
    int k = inf.readInt(1, m);
    for(int j = 1; j <= k; j++){
      int sid = inf.readInt(1, m);
      v[sid].push_back(i);
    }
  }

  int cnt = ouf.readInt(1, m);
  int totcost = 0;
  for(int i = 1; i <= cnt; i++){
    int sid = ouf.readInt(1, m);
    totcost += cost[sid];
    for(int j = 0; j < v[sid].size(); j++){
      vis[v[sid][j]] = 1;
    }
  }

  for(int i = 1; i <= n; i++){
    if(!vis[i])quitf(_wa, "Invalid answer");
  }

  // quitf(_ok, "cost is %d", totcost);

  int ref = ans.readInt();
  double score = (2.0*ref-1.0*totcost)/(1.0*ref);
  score = max(score, 0.0);
  double unbounded_score = std::max(0.0, score);
  score = min(score, 1.0);
  quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
}