#include "testlib.h"
#include <vector>
#include <cassert>

using namespace std;

const int MAXN=2010;
int n,C[MAXN][MAXN],p[MAXN],a[MAXN],ck[MAXN];
double subtask(){
    n=inf.readInt();
    for(int i=1;i<=n;i++){
        // std::string s=inf.readString();
        // assert(s.length()>=n);
        // for(int j=0;j<n;j++)
        //     C[i][j+1]=s[j]-'0';
        for(int j=1;j<=n;j++){
            char c=inf.readChar();
            // int cnt=0;
            while((c!='0')&&(c!='1')){
                c=inf.readChar();
                // cnt++;
                // std::cerr<<"'"<<c<<"'"<<std::endl;
                // if(cnt>=10) break;
            }
            // std::cerr<<"here "<<cnt<<std::endl;
            C[i][j]=c-'0';
        }
    }

    for(int i=1;i<=n;i++){
        p[i]=ouf.readInt();
        ck[i]=p[i];
        if(p[i]<1||p[i]>n) quitf(_wa, "Invalid p[%d]",i);
    }
    sort(ck+1,ck+n+1);
    for(int i=1;i<=n;i++)
        if(ck[i]!=i) quitf(_wa, "Invalid permutation");

    for(int i=1;i<=n;i++)
        if(i==n) a[i]=C[p[i]][p[1]];
        else a[i]=C[p[i]][p[i+1]];
    int op=0;
    for(int i=1;i<n;i++)
        if(a[i]!=a[i+1]) op++;
    if(op>1) quitf(_wa, "wrong answer");

    long long base_value=ans.readLong();
    long long best_value=ans.readLong();
    long long value=0;
    for(int i=1,j=n;i<=n;i++,j--)
        value+=1ll*j*p[i];

    double score_unbounded=max(0.0,1.0*(base_value-value)/(base_value-best_value));
    return score_unbounded;
}
int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    int T=ans.readInt();
    double sum=0.0,sum_unbounded=0.0,sub_score,tot=T;
    while(T){
        T--;
        sub_score=subtask();
        sum+=min(1.0,sub_score);
        sum_unbounded+=sub_score;
    }
    double score_ratio=sum/tot;
    double unbounded_ratio=sum_unbounded/tot;
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", (long long)(score_ratio*100), score_ratio, unbounded_ratio);
}