#include "testlib.h"
#include <iostream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <algorithm>

using namespace std;
#define MAX 2000
int cun[2010],p[2010],totc,xx;
inline int read()
{
    int x=0,t=1;char ch=getchar();
    while((ch<'0'||ch>'9')&&ch!='-')ch=getchar();
    if(ch=='-')t=-1,ch=getchar();
    while(ch<='9'&&ch>='0')x=x*10+ch-48,ch=getchar();
    return x*t;
}
struct Node
{
    int ch[2];
    int ff,v;
    int size;
    int mark;
    void init(int x,int fa)
        {
            ff=ch[0]=ch[1]=0;
            size=1;v=x;ff=fa;
        }
}t[MAX];
int N,root,M,tot;
inline void pushup(int x)
{
    t[x].size=t[t[x].ch[0]].size+t[t[x].ch[1]].size+1;
}
inline void pushdown(int x)
{
    if(t[x].mark)
    {
        t[t[x].ch[0]].mark^=1;
        t[t[x].ch[1]].mark^=1;
        t[x].mark=0;
        swap(t[x].ch[0],t[x].ch[1]);
    }
}
inline void rotate(int x)
{
    int y=t[x].ff;
    int z=t[y].ff;
    int k=t[y].ch[1]==x;
    t[z].ch[t[z].ch[1]==y]=x;
    t[x].ff=z;
    t[y].ch[k]=t[x].ch[k^1];
    t[t[x].ch[k^1]].ff=y;
    t[x].ch[k^1]=y;
    t[y].ff=x;
    pushup(y);pushup(x);
}
inline void Splay(int x,int goal)
{
    while(t[x].ff!=goal)
    {
        int y=t[x].ff;int z=t[y].ff;
        if(z!=goal)
            (t[z].ch[1]==y)^(t[y].ch[1]==x)?rotate(x):rotate(y);
        rotate(x);
    }
    if(goal==0)root=x;
}
inline void insert(int x)
{
    int u=root,ff=0;
    while(u)ff=u,u=t[u].ch[x>t[u].v];
    u=++tot;
    if(ff)t[ff].ch[x>t[ff].v]=u;
    t[u].init(x,ff);
    Splay(u,0);
}
inline int Kth(int k)
{
    int u=root;
    while(233)
    {
        pushdown(u);
        if(t[t[u].ch[0]].size>=k)u=t[u].ch[0];
        else if(t[t[u].ch[0]].size+1==k)return u;
        else k-=t[t[u].ch[0]].size+1,u=t[u].ch[1];
    }
}
void write(int u)
{
    pushdown(u);
    if(t[u].ch[0])write(t[u].ch[0]);
    if(t[u].v>1&&t[u].v<N+2)cun[++totc]=p[t[u].v-1];
    if(t[u].ch[1])write(t[u].ch[1]);
}
inline void Work(int l,int r)
{
    l=Kth(l);
    r=Kth(r+2);
    Splay(l,0);
    Splay(r,l);
    t[t[t[root].ch[1]].ch[0]].mark^=1;
}
void che(int x,int y)
{
	if(x>y)
		swap(x,y);
	if(x<1)
		quitf(_wa,"Your answer is over permitted!");
	if(y>N)
		quitf(_wa,"Your answer is over permitted!");
	if(y!=x+xx && y!=x+xx-2)
		quitf(_wa,"Your answer isn't legal!");
	return;
}
int main(int argc,char* argv[])
{
	registerTestlibCmd(argc,argv);
	int x,y,rr;
	xx=ouf.readInt();
    N=inf.readInt();M=ouf.readInt();
	rr=M;
	if(rr>N*200)
		quitf(_wa,"your reverse is more than limit.");
	for(int i=1;i<=N;i++)p[i]=inf.readInt();
    for(int i=1;i<=N+2;++i)insert(i);
    while(M--)
    {
        int l=ouf.readInt(),r=ouf.readInt();
		che(l,r);
        Work(l,r);
    }
    write(root);
	for(int i=1;i<=N;i++)
	{
		if(i!=cun[i])
			quitf(_wa,"Your answer isn't right!");
	}
	
	// Calculate score based on number of operations
	// Operations count rr (M) ranges from optimal to maximum (N*20)
	// Score decreases linearly as rr increases
	double baseline = N*20.0;  // Optimal number of operations (at least N operations needed)
	double max_ops = 200.0 * N;  // Maximum acceptable operations
	
	// Calculate score (0.0 to 1.0)
	double score_ratio;
	if (rr <= baseline) {
		score_ratio = 1.0;  // Full score for optimal or better
	} else {
		// Linear decrease from 1.0 to 0.0 as rr goes from baseline to max_ops
		score_ratio = max(0.0, 1.0 - (1.0 * (rr - baseline) / (max_ops - baseline)));
	}
	
	double unbounded_ratio = score_ratio;  // In this case, score is already bounded
	
	quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f", rr, score_ratio, unbounded_ratio);
	
    return 0;
}

