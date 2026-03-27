#include "testlib.h"
#include <iostream>
#include <vector>
#include <algorithm>
#include <string>
#include <map>

using namespace std;

int bits(long long val){
  for(int i = 60; i >= 0; i--){
    if((val>>i)&1ll)return i+1;
  }
  return 0;
}

int modPow(long long a, long long d, long long n){
  __int128 r = 1;
  __int128 x = a;
  int ret = 0;
  for(int i = 0; i < 60; i++){
    int bx = bits(x)+1;
    if(d&(1ll<<i)){
      ret += (bits(r)+1)*bx;
      r = r*x%n;
    }
    ret += bx*bx;
    x = x*x%n;
  }
  return ret;
}

int main(int argc, char *argv[]) {
  /*
   * inf: input
   * ouf: contestant output
   * ans: standard output
   */
  registerInteraction(argc, argv);

  long long n = inf.readLong(), d = inf.readLong();
  cout.flush();
  cout<<n<<endl;
  cout.flush();
  for(int i = 1; i <= 30001; i++){
    string operation = ouf.readWord();
    if(operation[0] == '?'){
      long long a = ouf.readLong(0, n-1);
      cout<<modPow(a, d, n)<<endl;
      cout.flush();
    }
    else if(operation[0] == '!'){
      long long answer = ouf.readLong();
      if(answer == d){
        double score = (30000.0-1.0*(i-1.0))/(30000.0-4000.0);
        double unbounded_ratio = max(0.0, (30000.0-1.0*(i-1.0))/(30000.0-4000.0));
        score = min(score, 1.0);
        score = max(score, 0.0);
        quitp(score, "Ratio: %.3lf, RatioUnbounded: %.3lf", score, unbounded_ratio);
      }
      else{
        quitf(_wa, "Incorrect d");
      }
    }
    else{
      quitf(_wa, "Invalid operation");
    }
  }
  quitf(_wa, "Too many queries");
}