#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;

vector<pair<int, int> >v[150];
int l, r;
int in[150], out[150];
int cnt = 0;
int vis[1000010];

void dfs(int x, int val){
  if(out[x] == 0){
    cnt++;
    if(cnt > 1e6)quitf(_wa, "too many roads");
    if(val < l || val > r) quitf(_wa, "number outside interval");
    vis[val]++;
    if(vis[val] > 1)quitf(_wa, "repeated roads");
    return;
  }
  for(int i = 0; i < out[x]; i++){
    dfs(v[x][i].first, val*2+v[x][i].second);
  }
}

int main(int argc, char *argv[]) {
  /*
   * inf：输入
   * ouf：选手输出
   * ans：标准输出
   */
  registerTestlibCmd(argc, argv);

  l = inf.readInt(), r = inf.readInt();

  int n = ouf.readInt(1, 100);
  for(int i = 1; i <= n; i++){
    out[i] = ouf.readInt(0, 200);
    for(int j = 1; j <= out[i]; j++){
      int a = ouf.readInt(1, n), val = ouf.readInt(0, 1);
      if(a == i)quitf(_wa, "self-loop");
      v[i].push_back(make_pair(a, val));
      in[a]++;
    }
  }

  // 1 in 0 and 1 out 0, no leading 0
  int cnt1 = 0, cnt2 = 0;
  for(int i = 1; i <= n; i++){
    if(in[i] == 0)cnt1++;
    if(out[i] == 0)cnt2++;
    if(in[i] == 0){
      for(int j = 0; j < out[i]; j++){
        if(v[i][j].second == 0)quitf(_wa, "leading 0");
      }
    }
  }
  if(cnt1 != 1 || cnt2 != 1)quitf(_wa, "more than one indegree or outdegree 0");

  for(int i = 1; i <= n; i++){
    if(in[i] == 0)dfs(i, 0);
  }
  for(int i = l; i <= r; i++){
    if(vis[i] == 0)quitf(_wa, "number not represented");
  }

  double score = (100.0-1.0*n)/(100.0-50.0);
  score = max(score, 0.0);
  double unbounded_score = score;
  score = min(score, 1.0);
  quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
}