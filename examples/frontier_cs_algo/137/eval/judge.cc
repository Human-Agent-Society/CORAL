#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

/* ------------------- Grid structure & validation ------------------- */

struct Grid {
    int n = 0, m = 0;
    vector<string> a;                 // '0'/'1' grid
    int ones = 0;
    vector<pair<int,int>> idx2rc;     // compact index -> (r,c) for '1' cells
    vector<int> rc2idx;               // size n*m: -1 if wall, else compact index
    array<vector<int>,4> mv;          // move maps for U,D,L,R over compact indices
};

static const int DR[4] = {-1, +1, 0, 0}; // U,D,L,R
static const int DC[4] = { 0,  0,-1, +1};

static void fail_invalid(const char* who, const string& msg) {
    quitf(_wa, "%s grid invalid: %s", who, msg.c_str());
}

static void read_grid_from_stream(const char* who, InStream& st, Grid& G) {
    G.n = st.readInt(1, 20, "n");
    G.m = st.readInt(1, 20, "m");
    G.a.resize(G.n);
    for (int i = 0; i < G.n; ++i) {
        G.a[i] = st.readToken();
        if ((int)G.a[i].size() != G.m)
            fail_invalid(who, "row length mismatch at row " + to_string(i+1));
        for (char c : G.a[i]) if (c!='0' && c!='1')
                fail_invalid(who, "non 0/1 character in row " + to_string(i+1));
    }

    // Build compact indexing for '1' cells
    G.ones = 0;
    G.rc2idx.assign(G.n * G.m, -1);
    G.idx2rc.clear();
    for (int r=0;r<G.n;++r) for (int c=0;c<G.m;++c) if (G.a[r][c]=='1') {
                G.rc2idx[r*G.m + c] = G.ones++;
                G.idx2rc.push_back({r,c});
            }
    if (G.ones < 2) fail_invalid(who, "must have at least two '1' cells");

    // Connectivity (4-neighbor) via BFS
    vector<vector<int>> vis(G.n, vector<int>(G.m, 0));
    int sr=-1, sc=-1;
    for (int r=0;r<G.n && sr==-1;++r)
        for (int c=0;c<G.m && sr==-1;++c)
            if (G.a[r][c]=='1') { sr=r; sc=c; }
    queue<pair<int,int>> q;
    q.push({sr,sc}); vis[sr][sc]=1;
    int reached=0;
    while(!q.empty()){
        auto [r,c]=q.front(); q.pop(); ++reached;
        for (int k=0;k<4;++k){
            int nr=r+DR[k], nc=c+DC[k];
            if (nr<0||nr>=G.n||nc<0||nc>=G.m) continue;
            if (G.a[nr][nc]!='1' || vis[nr][nc]) continue;
            vis[nr][nc]=1; q.push({nr,nc});
        }
    }
    if (reached != G.ones) fail_invalid(who, "1-cells not connected");

    // Acyclic: edges between adjacent '1's (right+down) must be ones-1
    long long edges=0;
    for (int r=0;r<G.n;++r) for (int c=0;c<G.m;++c) if (G.a[r][c]=='1') {
                if (r+1<G.n && G.a[r+1][c]=='1') ++edges;
                if (c+1<G.m && G.a[r][c+1]=='1') ++edges;
            }
    if (edges != (long long)G.ones - 1)
        fail_invalid(who, "1-cells are not a tree (edges != nodes-1)");

    // Precompute move maps for directions U,D,L,R
    for (int d=0; d<4; ++d) G.mv[d].assign(G.ones, -1);
    for (int idx=0; idx<G.ones; ++idx) {
        auto [r,c] = G.idx2rc[idx];
        for (int d=0; d<4; ++d) {
            int nr=r+DR[d], nc=c+DC[d];
            int to = idx; // stay by default
            if (0<=nr && nr<G.n && 0<=nc && nc<G.m && G.a[nr][nc]=='1')
                to = G.rc2idx[nr*G.m + nc];
            G.mv[d][idx] = to;
        }
    }
}

/* ------------------- Simulation ------------------- */
/*
   Start with all K '1'-cells occupied. For each move, map the set via mv[d] with de-dup.
   Early exit if set size becomes 1 (remains 1 forever).
*/

static int score_on_grid(const Grid& G, int t, const vector<string>& seqs) {
    const int K = G.ones;

    // de-dup stamps
    vector<int> stamp(K, 0);
    int curStamp = 1;

    vector<int> cur; cur.reserve(K);
    vector<int> nxt; nxt.reserve(K);

    auto step_dir = [&](int dir){
        nxt.clear();
        int myStamp = curStamp++;
        for (int x : cur) {
            int y = G.mv[dir][x];
            if (stamp[y] != myStamp) {
                stamp[y] = myStamp;
                nxt.push_back(y);
            }
        }
        cur.swap(nxt);
    };

    int not_gathered = 0;
    for (int s=0; s<t; ++s) {
        const string& str = seqs[s];
        cur.clear(); cur.reserve(K);
        for (int i=0;i<K;++i) cur.push_back(i);

        for (char ch : str) {
            if ((int)cur.size() <= 1) break;
            int dir = (ch=='U'?0 : ch=='D'?1 : ch=='L'?2 : 3);
            step_dir(dir);
        }
        if ((int)cur.size() != 1) ++not_gathered;
    }
    return not_gathered;
}

/* ------------------- Checker main ------------------- */

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // participant grid from ouf
    Grid part;
    read_grid_from_stream("participant", ouf, part);

    // optimal grid from ans
    Grid opt;
    read_grid_from_stream("answer", ans, opt);

    // t and t strings from inf
    int t = inf.readInt(1, 1000000000, "t");
    vector<string> seqs(t);
    for (int i=0;i<t;++i) {
        seqs[i] = inf.readToken();
        for (char c : seqs[i]) {
            if (c!='U' && c!='D' && c!='L' && c!='R')
                quitf(_fail, "Invalid move character in string %d", i+1);
        }
    }

    // simulate
    int part_score = score_on_grid(part, t, seqs);
    int opt_score  = score_on_grid(opt,  t, seqs);

    // ratio
    double score_ratio, unbounded_ratio;
    if (opt_score == 0) {
        score_ratio = (part_score == 0 ? 1.0 : 0.0);
        unbounded_ratio = score_ratio;
    } else {
        score_ratio = (double)part_score / (double)opt_score;
        if (score_ratio < 0.0) score_ratio = 0.0;
        unbounded_ratio = score_ratio;
        if (score_ratio > 1.0) score_ratio = 1.0;
    }

    long long participant_value = part_score; // match required message format
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", participant_value, score_ratio, unbounded_ratio);
}
