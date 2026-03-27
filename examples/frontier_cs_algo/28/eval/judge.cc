#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>
#include <map>

using namespace std;

string s[30][1010];
char current[15];
int num[30];
int cnt = 0;
map<string, int>vis;

void dfs(int now, int start){
  if(cnt >= 1000)return;
  if(now >= 10){
    cnt++;
    for(int i = 0; i < 10; i++){
      s[start][cnt] += current[i];
    }
    return;
  }
  if(now == 0){
    current[now] = (char)('a'+start);
    dfs(now+1, start);
  }
  else{
    for(int i = 0; i < 26; i++){
      current[now] = (char)('a'+i);
      dfs(now+1, start);
    }
  }
}

int main(int argc, char *argv[]) {
  /*
   * inf: input
   * ouf: contestant output
   * ans: standard output
   */
  registerInteraction(argc, argv);
  
  for(int i = 0; i < 26; i++){
    cnt = 0;
    dfs(0, i);
  }
  int t = inf.readInt(), n = inf.readInt();
  for(int i = 0; i < 26; i++){
    num[i] = inf.readInt();
  }
  cout<<t<<endl;
  cout.flush();
  cout<<n<<endl;
  cout.flush();
  int sumk = 0;
  for(int i = 1; i <= 4000; i++){
    string operation = ouf.readWord();
    if(operation == "query"){
      string qs = ouf.readWord();
      if(qs.length() >= 10)quitf(_wa, "Invalid query");
      int k = ouf.readInt(1, n); 
      sumk += k;
      int start = qs[0]-'a';

      int match_cnt = 0;
      string ret[1010];
      for(int j = 1; j <= num[start]; j++){
        int match = 1;
        for(int t = 0; t < qs.length(); t++){
          if(s[start][j][t] != qs[t])match = 0;
        }
        if(match){
          match_cnt++;
          ret[match_cnt] = s[start][j];
          if(match_cnt == k)break;
        }
      }
      cout<<match_cnt<<" ";
      for(int j = 1; j <= match_cnt; j++){
        cout<<ret[j]<<" ";
      }
      cout<<endl;
      cout.flush();
    }
    else if(operation == "answer"){
      for(int j = 1; j <= n; j++){
        string answers = ouf.readWord();
        int start = answers[0]-'a';
        if(answers > s[start][num[start]])quitf(_wa, "Invalid answer");
        if(vis[answers])quitf(_wa, "Repeated answer");
        vis[answers] = 1;
      }
      double score = (4000.0-1.0*sumk)/(4000.0-2400.0);
      double unbounded_score = max(0.0, score);
      score = min(score, 1.0);
      score = max(score, 0.0);
      quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_score);
    }
    else{
      quitf(_wa, "Invalid operation");
    }
  }
  quitf(_wa, "Too many queries");
}