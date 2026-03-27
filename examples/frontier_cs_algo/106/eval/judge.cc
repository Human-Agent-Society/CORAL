#include "testlib.h"

#include <bits/stdc++.h>

constexpr int MAXN = 600;
constexpr int MAXQ = 5000;

using namespace std;

struct DSU {
	std::vector<int> f, siz;

	DSU() {}
	DSU(int n) {
		init(n);
	}

	void init(int n) {
		f.resize(n);
		std::iota(f.begin(), f.end(), 0);
		siz.assign(n, 1);
	}

	int find(int x) {
		while (x != f[x]) {
			x = f[x] = f[f[x]];
		}
		return x;
	}

	bool same(int x, int y) {
		return find(x) == find(y);
	}

	bool merge(int x, int y) {
		x = find(x), y = find(y);
		if (x == y) {
			return false;
		}
		f[y] = x;
		siz[x] += siz[y];
		return true;
	}

	int size(int x) {
		return siz[find(x)];
	}
};

int main(int argc, char ** argv){
	registerInteraction(argc, argv);
	int n = inf.readInt();
    int m = inf.readInt();
    vector<bitset<MAXN>> E(n);
    DSU dsu(2 * n);
    for (int i = 0; i < m; i++) {
        int u = inf.readInt();
        int v = inf.readInt();
        --u; --v;
        E[u].set(v);
        E[v].set(u);
        dsu.merge(n + u, v);
        dsu.merge(u, n + v);
    }

    bool flag = true;
    for (int i = 0; i < n; i++) {
    	flag &= !dsu.same(i, n + i);
    }

    cout << n << endl;
    cout.flush();
    
    for (int q = 1; q <= MAXQ + 1; ++q) {
        string S = ouf.readToken();
        if (S == "?") {
            if (q > MAXQ) { cout << "-1\n"; quitf(_wa, "too many queries"); }
            
            bitset<MAXN> F;
            int k = ouf.readInt();
            if (k < 1 || k > n) { cout << "-1\n"; quitf(_wa, "query %d: k=%d out of range", q, k); }

            for (int j = 0; j < k; j++) {
                int b = ouf.readInt();
                if (b < 1 || b > n) { cout << "-1\n"; quitf(_wa, "query %d: v[%d]=%d out of range", q, j+1, k); }
                if (F[b-1]) { cout << "-1\n"; quitf(_wa, "query %d: vertex %d appears twice", q, b); }
                F.set(b-1);
            }

            int ans = 0;
            for (int i = 0; i < n; i++) if (F[i]) ans += (E[i]&F).count();
            cout << ans/2 << endl;
            cout.flush();
            
        } else if (S == "N" || S == "Y") {
        	if ((S == "Y") != flag) {
        		quitp(0., "Wrong guess 0. Ratio: 0.0000");
        	}

            int r = ouf.readInt();
            if (r < 0 || r > n) { cout << "-1\n"; quitf(_wa, "answer %d out of range", r); }
            
            std::vector<int> v(r);
            for (int i = 0; i < r; i++) {
                v[i] = ouf.readInt();
                if (v[i] < 1 || v[i] > n) { cout << "-1\n"; quitf(_wa, "a[%d]=%d out of range", i+1, v[i]); }
                v[i]--;
            }

            if (S == "Y") {
            	std::array<std::vector<int>, 2> a;
            	for (int i = 0; i < n; i++) {
            		a[dsu.same(i, 0)].push_back(i);
            	}

                std::sort(v.begin(), v.end());
            	if (std::find(a.begin(), a.end(), v) != a.end()) {
            		double ratio = 1. * (MAXQ - q) / MAXQ;
            		quitp(ratio, "Correct guess Y. Ratio: %.4f", ratio);
            	} else {
            		quitp(0., "Wrong guess 1. Ratio: 0.0000");
            	}
            } else {
            	if (r % 2 == 0) {
            		quitp(0., "Wrong guess 2. Ratio: 0.0000");
            	}
            	for (int i = 0; i < r; i++) {
            		if (!E[v[i]][v[(i + 1) % r]]) {
            			quitp(0., "Wrong guess 3. Ratio: 0.0000");
            		}
            	}

            	double ratio = 1. * (MAXQ - q) / MAXQ;
            	quitp(ratio, "Correct guess N. Ratio: %.4f", ratio);
            }
        
        } else {
            cout << "-1\n"; quitf(_wa, "invalid query");
        }
    }
}