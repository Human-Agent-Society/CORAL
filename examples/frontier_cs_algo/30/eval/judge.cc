#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;

vector<int>v[5010];
int fa[5010], depth[5010];
int X[5010], Y[5010];

void dfs(int x, int f){
  fa[x] = f;
  for(int i = 0; i < v[x].size(); i++){
    int y = v[x][i];
    if(y==f)continue;
    depth[y] = depth[x]+1;
    dfs(y, x);
  }
}

int main(int argc, char *argv[]) {
  /*
   * inf: input
   * ouf: contestant output
   * ans: standard output
   */
  registerInteraction(argc, argv);

  int t = inf.readInt(1, 1), n = inf.readInt(5000, 5000);
  for(int i = 1; i < n; i++){
    int x = inf.readInt(1, n), y = inf.readInt(1, n);
    X[i] = x, Y[i] = y;
    v[x].push_back(y);
    v[y].push_back(x);
  }
  depth[1] = 0;
  dfs(1, 1);
  int target = inf.readInt(1, n);
  cout<<t<<endl;
  cout.flush();
  cout<<n<<endl;
  cout.flush();
  for(int i = 1; i < n; i++){
    cout<<X[i]<<" "<<Y[i]<<endl;
    cout.flush();
  }
  int sum_depth = 0;
  for(int i = 1; i <= 500; i++){
    char s = ouf.readChar();
    if(s == '?'){
      ouf.readSpace();
      int x = ouf.readInt(1, n);
      sum_depth += depth[x];
      ouf.readEoln();
      int y = target;
      while(y != 1 && y != x){
        y = fa[y];
      }
      if(y != x){
        cout<<0<<endl;
        cout.flush();
        target = fa[target];
      }
      else{
        cout<<1<<endl;
        cout.flush();
      }
    }
    else if(s == '!'){
      ouf.readSpace();
      int guess = ouf.readInt(1, n);
      ouf.readEoln();
      ouf.readEof();
      if(guess == target){
        int best = ans.readInt();
        double score = (3.0*best-1.0*sum_depth)/(2.0*best); // Get full score if less than 1.5*best, get half if less than 2.0*best
        double unbounded_score = max(0.0, score);
        score = min(score, 1.0);
        score = max(score, 0.0);
        quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
      }
      else{
        quitf(_wa, "Wrong node, expected %d, output %d", target, guess);
      }
    }
    else{
      quitf(_wa, "Invalid operation");
    }
  }
  
  quitf(_wa, "Too many queries");
}