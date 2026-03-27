#include "testlib.h"
#include <bits/stdc++.h> 
using namespace std;

const int maxn = 35;

int n, m;
int sr, sc, er, ec;
int vis[maxn][maxn];
string op, s[maxn];

inline bool isPalin(string str) {
	for (int i = 0; i < str.size(); ++i)
		if (str[i] != str[str.size() - 1 - i]) return false;
	return true;
}

inline void dfs(int x, int y) {
	if (vis[x][y]) return;
	vis[x][y] = 1;
	if (x - 1 >= 0 && s[x - 1][y] != '0') dfs(x - 1, y);
	if (x + 1 < n && s[x + 1][y] != '0') dfs(x + 1, y);
	if (y - 1 >= 0 && s[x][y - 1] != '0') dfs(x, y - 1);
	if (y + 1 < m && s[x][y + 1] != '0') dfs(x, y + 1);
}

int main(int argc, char **argv){
	registerTestlibCmd(argc, argv);
	n = inf.readInt(), m = inf.readInt();
	inf.readString();
	for (int i = 0; i < n; ++i)
		s[i] = inf.readString();
	sr = inf.readInt(), sc = inf.readInt(), er = inf.readInt(), ec = inf.readInt();
	--sr, --sc, --er, --ec;
	op = ouf.readString();
	
	if (op == "-1") {
		dfs(sr, sc);
		for (int i = 0; i < n; ++i) for (int j = 0; j < m; ++j)
			if (s[i][j] == '1' && !vis[i][j])
				quitf(_ok, "Correct.");
		quitp(0.0, "Answer exists but -1 found.");
	}
	
	if (!isPalin(op)) {
		quitp(0.0, "Not palindrome.");
	}
	else {
		vis[sr][sc] = 1;
		for (auto c: op) {
			int nr = sr, nc = sc;
			if (c == 'L' && nc - 1 >= 0 && s[nr][nc - 1] != '0') --nc;
			else if (c == 'R' && nc + 1 < m && s[nr][nc + 1] != '0') ++nc;
			else if (c == 'U' && nr - 1 >= 0 && s[nr - 1][nc] != '0') --nr;
			else if (c == 'D' && nr + 1 < n && s[nr + 1][nc] != '0') ++nr;
			sr = nr, sc = nc;
			vis[sr][sc] = 1;
		}
		if (sr != er || sc != ec) {
			quitp(0.0, "Not ending at (er, ec)");
		}
		int blank = 0;
		for (int i = 0; i < n; ++i) for (int j = 0; j < m; ++j) {
			blank += (s[i][j] == '1');
			if (s[i][j] == '1' && !vis[i][j]) {
				quitp(0.0, "Blank cells unvisited");
			}
		}
		double pnt = 1.0, unbounded_pnt = 1.0;
		int bound = 12 * blank * max(n, m);
		if (op.size() <= bound) {
			// quitf(_ok, "Correct.");
			unbounded_pnt -= 1.0 * (op.size() - bound) / bound;
		}
		else {
			pnt -= 1.0 * (op.size() - bound) / bound;
			pnt = max(pnt, 0.0);
			unbounded_pnt = pnt;
		}
		char mes[30];
		sprintf(mes, "Ratio: %lf, RatioUnbounded: %lf", pnt, unbounded_pnt);
		quitp(pnt, "%s", mes);
	}
	return 0;
}

