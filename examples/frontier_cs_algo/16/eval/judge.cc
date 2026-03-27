#include <bits/stdc++.h>
#include "testlib.h"
using namespace std;
const int qlim=500;
double eva(int x) {
    if (x > 500) return 0.0;

    if (x <= 40) {
        // Phase 1: Minimal score decrease
        return 100.0 - (x * x) / 200.0;
    } else if (x <= 100) {
        // Phase 2: Accelerated decay, exponential function
        double k = 0.0329013504337; // Precisely calculated constant
        return 72.0 * exp(-k * (x - 40)) + 20.0;
    } else {
        // Phase 3: Slower decay, quadratic function
        double t = (x - 100) / 400.0; // From 0 to 1
        return 30.0 * pow(1.0 - t, 2.0);
    }
}
int main(int argc, char* argv[])
{
	registerInteraction(argc, argv);
	
	int T = inf.readInt();
	cout<<T<<endl;
	double score=1.0;
	int mx=0;
	for(int tt=1;tt<=T;tt++)
	{
	    // setTestCase(tt);
		int queries = 0;
		int n = inf.readInt();
		cout<<n<<endl;
		auto getdis0=[&](int x,int y)
		{
			if(x>y)swap(x,y);
			return min(y-x,n-y+x);
		};
		auto getdis=[&](int u,int v,int x,int y)
		{
			return min({getdis0(x,y),getdis0(x,u)+1+getdis0(v,y),getdis0(x,v)+1+getdis0(u,y)});
		};
		int u = inf.readInt();
		int v = inf.readInt();
		while (true)
		{
			string ty = ouf.readToken();
			if(ty!="?" && ty!="!")
			{
				quitf(_wa, "You should either \"?\" or \"!\".");
			}
			int x = ouf.readInt(1,n),y = ouf.readInt(1,n);
			if(ty=="!")
			{
			    tout << queries << endl;
				if(min(x,y)==min(u,v) and max(x,y)==max(u,v))
				{mx=max(mx,queries);
					cout<<1<<endl;
					score=min(score,eva(queries)/100.0);
					break; // breaks while(true)
				}
				else
				{
					cout<<-1<<endl;
					quitf(_wa, "Wrong answer n=%d, actual=%d-%d, guessed=%d-%d",n,u,v,x,y);
				}
			} else {
                queries++;
				
                if(queries>qlim) quitf(_wa,"Too many queries: %d",queries);
                cout<<getdis(u,v,x,y)<<endl;
            }
		}
	}
	cerr << "[Interactor] used=" << mx << "\n";
	quitp(score, "Correct Guess. Ratio: %.4f", score);
}
