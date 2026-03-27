#include "testlib.h"
#include <cassert>
using namespace std;
int q[1100];
int query_count = 0, R, H, get_count = 0;
constexpr int query_limit=75, max_position=1000;
int vis[1100],wait_ans[1100];

double cal_score(int rmax){
    double score=0.0;
    if(rmax<=30) score=-1.0*20/3*rmax+1.0*820/3;
    else if(30<rmax<=35) score=-1.0*4*rmax+1.0*580/3;
    else if(35<rmax<=40) score=-1.0*8/3*rmax+1.0*440/3;
    else if(40<rmax<=60) score=-1.0*4/3*rmax+1.0*280/3;
    else if(60<rmax<=75) score=1.0*40/3;
    return score/100;
}

bool valid_pos(int x){
    return 1<=x&&x<=max_position;
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    R=inf.readInt(),H=inf.readInt();
    int ans_a=ans.readInt(),ans_b=ans.readInt();
    if(ans_a>ans_b) swap(ans_a, ans_b);
    assert(valid_pos(ans_a) && valid_pos(ans_b));
    
    println(R,H);
    while(true){
        char ch=ouf.readChar();
        while(ch!='!' && ch!='?' && ch!= '@'){
            ch=ouf.readChar();
        }
        if (ch=='?'){
            query_count++;
            if(query_count>query_limit) quitf(_wa, "Too many sends");
            int len=ouf.readInt(),flag=0;
            if(len<0) quitf(_wa, "Invalid length");
            for(int i=1;i<=len;i++){
                q[i]=ouf.readInt();
                if(!valid_pos(q[i])) quitf(_wa, "Invalid position");
                if(vis[q[i]]==query_count) quitf(_wa, "Repeat position");
                vis[q[i]]=query_count;
                if(q[i]==ans_a || q[i]==ans_b) flag=1;
            }
            wait_ans[++wait_ans[0]]=flag;
        }
        else if (ch=='@'){
            get_count++;
            if (get_count > H) quitf(_wa, "Too many gets");
            println(wait_ans,wait_ans+wait_ans[0]+1);
            wait_ans[0]=0;
        }
        else{
            int a=ouf.readInt(),b=ouf.readInt();
            if(a>b) swap(a,b);
            if(a!=ans_a || b!=ans_b) quitf(_wa, "wrong guess (%d, %d), should be (%d, %d)",a,b,ans_a,ans_b);
            break;
        }
    }
    double unbounded_ratio=cal_score(query_count);
    double score_ratio = std::min(1.0, unbounded_ratio);
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", (long long)(score_ratio*100), score_ratio, unbounded_ratio);
    return 0;
}
