#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>
#include <set>

using namespace std;

set<int>s[5];

int main(int argc, char *argv[]) {
  /*
   * inf: input
   * ouf: player output
   * ans: standard output
   */
  registerTestlibCmd(argc, argv);

  int n = inf.readInt();
  for(int i = 1; i <= n; i++){
    s[1].insert(i);
  }
  int m = ouf.readInt();
  for(int i = 1; i <= m; i++){
    int a = ouf.readInt(1, 3), b = ouf.readInt(1, 3);
    if(a == b)quitf(_wa, "Same basket");
    if(s[a].empty())quitf(_wa, "Empty basket a");
    int mida = (s[a].size()+2)/2;
    set<int>::iterator it;
    for(it = s[a].begin(); it != s[a].end(); it++){
      mida--;
      if(mida == 0)break;
    }
    int val = (*it);
    s[a].erase(val);
    s[b].insert(val);
    int midb = (s[b].size()+2)/2;
    for(it = s[b].begin(); it != s[b].end(); it++){
      midb--;
      if(midb == 0)break;
    }
    if((*it) != val)quitf(_wa, "Invalid target basket b on %d operation", i);
  } 
  if(s[3].size()==n){
    int ref = ans.readInt();
    double score = (2.0*ref-1.0*m)/(1.0*ref);
    if (score < 0) score = 0.0;
    double unbounded_score = max(0.0, score);
    score = min(score, 1.0);
    score = max(score, 0.0);
    quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
  } 
  else quitf(_wa, "Invalid operation");
}