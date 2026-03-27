#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>
#include <map>

using namespace std;

int WrongPred[1010];

int main(int argc, char *argv[]) {
  /*
   * inf: input
   * ouf: contestant output
   * ans: standard output
   */
  registerInteraction(argc, argv);

  int n = inf.readInt(1, 1000), m = inf.readInt(1, 10000);
  cout.flush();
  cout<<n<<" "<<m<<endl;
  cout.flush();
  int wrongpred = 0;
  for(int i = 1; i <= m; i++){
    string pred = inf.readWord();
    int answer = inf.readInt(0, 1);
    for(int j = 0; j < n; j++){
      if(pred[j]-'0' != answer)WrongPred[j]++;
    }
    cout<<pred<<endl;
    cout.flush();
    int outpred = ouf.readInt(0, 1);
    if(outpred != answer)wrongpred++;
    cout<<answer<<endl;
    cout.flush();
  }
  int minwrongpred = m+1;
  for(int i = 0; i < n; i++){
    minwrongpred = min(minwrongpred, WrongPred[i]);
  }
  double score = (2.0*minwrongpred-1.0*wrongpred)/(1.0*minwrongpred);
  double unbounded_score = max(0.0, score);
  score = min(score, 1.0);
  score = max(score, 0.0);
  quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
}