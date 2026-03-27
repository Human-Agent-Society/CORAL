#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>
#include <map>

using namespace std;

int movecnt = 0, querycnt = 0;
int f[1100010];

int main(int argc, char *argv[]) {
  /*
   * inf：输入
   * ouf：选手输出
   * ans：标准输出
   */
  registerInteraction(argc, argv);

  int deep = inf.readInt(), seed = inf.readInt();
  memset(f, -1, sizeof(f));
  for(int i = 1; i <= deep; i++){
    int cur = -1;
    while(true){
      seed = (seed*998244353ll+97)%1000000009;
      cur = seed%3;
      if(cur != f[i-1])break;
    }
    f[i] = cur;
  }
  cout.flush();
  cout<<deep<<endl;
  cout.flush();
  while(true){
    string operation = ouf.readWord();
    if(operation == "move"){
      int c = ouf.readInt(0, 2);
      movecnt++;
      if(movecnt > 100000){
        quitf(_wa, "Too many moves");
      }
      if(c == f[deep]){
        deep--;
        if(deep == 0){
          cout<<1<<endl;
          cout.flush();
          double score = (5000.0/querycnt);// can be more strict
          double unbounded_ratio = max(0.0, (5000.0/querycnt));
          score = min(score, 1.0);
          score = max(score, 0.0);
          quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_ratio);
        }
        else{
          cout<<0<<endl;
          cout.flush();
        }
      }
      else{
        deep++;
        f[deep] = c;
        cout<<0<<endl;
        cout.flush();
      }
    }
    else if(operation == "query"){
      querycnt++;
      if(querycnt > 100000){
        quitf(_wa, "Too many queries");
      }
      cout<<deep<<endl;
      cout.flush();
    }
    else{
      quitf(_wa, "Invalid operation");
    }
  }
  quitf(_wa, "Exit not founded");
}