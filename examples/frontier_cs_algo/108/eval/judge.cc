#include "testlib.h"
#include <cassert>

int p[5100],q[5100];
int query_count = 0;
constexpr int query_limit=30000, full_score=1;
bool vis[5100];

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    int n=inf.readInt(),m=inf.readInt();
    for(int i=1;i<n;i++){
        p[i]=ans.readInt(),q[i]=p[i];
        if(p[i]<0||p[i]>=n*m) quitf(_wa, "Invalid input");
    }
    
    println(n,m);
    while(true){
        char ch=ouf.readChar();
        while(ch!='!' && ch!='?'){
            ch=ouf.readChar();
        }
        if (ch=='?'){
            query_count++;
            if(query_count>query_limit) quitf(_wa, "Too many queries");
            int x=ouf.readInt();
            int d=ouf.readInt();
            if(!(x>=0 && x<n)) quitf(_wa, "Invalid x");
            if(d==1){
                q[x]++;
                if(q[x]>=n*m) q[x]-=n*m;
            }
            else if(d==-1){
                q[x]--;
                if(q[x]<0) q[x]+=n*m;
            }
            else quitf(_wa, "Invalid d");

            for(int j=0;j<n;j++){
                for(int now=q[j],k=0;k<m;k++,now++){
                    now%=n*m;
                    vis[now]=true;
                }
            }
            int q_ans=0;
            for(int i=0;i<n*m;i++){
                if(vis[i]) vis[i]=0;
                else q_ans++;
            }
            println(q_ans);
        }
        else{
            for(int i=1;i<n;i++){
                int gue=ouf.readInt()+q[0];
                gue%=n*m;
                if(gue<0) gue+=n*m;
                if(gue!=q[i]) quitf(_wa, "wrong guess %d, %d and %d",i, q[i], gue);
            }
            break;
        }
    }
    double score=full_score*(1.0*(query_limit-query_count)/query_limit);
    quitp(score, "qurey count: %d, Ratio: %.4f",query_count, score);
    return 0;
}
