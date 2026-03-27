#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;
 
#define rep(i, a, b) for(int i = a; i < (b); ++i)
#define trav(a, x) for(auto& a : x)
#define all(x) x.begin(), x.end()
#define sz(x) (int)(x).size()
typedef long long ll;
typedef pair<int, int> pii;
typedef vector<int> vi;
typedef vector<vi> vvi;

int main(int argc, char *argv[]) {
  /*
   * inf: input file
   * ouf: contestant output
   * ans: standard output
   */
  registerTestlibCmd(argc, argv);


	int expected_ans = ans.readInt();
	int user_answer = ouf.readInt();
	double score = max(0.0, 1.0 - log2(abs(user_answer - expected_ans) + 1) / 10.0);
    
  quitp(score, "Ratio: %.4f, RatioUnbounded: %.4f", score, score);
}