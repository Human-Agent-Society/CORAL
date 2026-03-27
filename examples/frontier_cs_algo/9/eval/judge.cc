#include "testlib.h"
#include <vector>
#include <cassert>

using namespace std;

const int MAXN=1005;
int n,p[MAXN],vis[MAXN];
vector<pair<int,int> >e;
double subtask(){
    n=inf.readInt();
    e.clear();
    for(int i=1;i<=n;i++){
        p[i]=inf.readInt();
        vis[i]=0;
    }
    for(int i=1,u,v;i<n;i++){
        u=inf.readInt();
        v=inf.readInt();
        e.push_back(make_pair(u,v));
    }
    
    int base_value=ans.readInt();
    int best_value=ans.readInt();
    
    int m=ouf.readInt();
    if(m>base_value) quitf(_wa, "Too many operations!");
    for(int k,i=1;i<=m;i++){
        k=ouf.readInt();
        if(k<0 || k>=n) quitf(_wa, "Invalid number of edges in maching");
        for(int j=0,t,u,v;j<k;j++){
            t=ouf.readInt();
            if(t<=0 || t>=n) quitf(_wa, "Invalid edge idx");
            t--;
            u=e[t].first,v=e[t].second;
            //std::cerr<<t<<"     "<<u<<","<<v<<std::endl;
            if(vis[u]==i || vis[v]==i) quitf(_wa, "Invalid maching%d,%d  %d,%d",i,j,u,v);
            vis[u]=vis[v]=i;
            swap(p[u],p[v]);
        }
        //std::cerr<<std::endl;
    }
    for(int i=1;i<=n;i++){
        if(p[i]!=i) quitf(_wa, "wrong answer, node %d dismatch", i);
    }
    double score_unbounded=max(0.0,1.0*(base_value-m)/(base_value-best_value));
    return score_unbounded;
}
int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    int T=inf.readInt();
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