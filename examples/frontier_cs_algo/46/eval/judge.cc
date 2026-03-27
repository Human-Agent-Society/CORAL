#include "testlib.h"
#include <vector>
#include <string>
#include <deque>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
using namespace std;

/*
Job Shop Scheduling Checker (minimization).

Input (.in):
  J M
  J lines each with 2*M integers: (m_0 p_0 m_1 p_1 ... m_{M-1} p_{M-1})
  - Machines and jobs are 0-based.
  - Each job uses every machine exactly once in the listed order.
  - p_k > 0.

Contestant Output:
  M lines, line m has J integers: a permutation of 0..J-1 specifying the processing order on machine m.

Answer (.ans):
  Two integers: Baseline B and Best T. For this problem (lower-is-better), T is fixed to 0 in all test files,
  and B is a feasible makespan upper bound from a simple heuristic. The checker does not assume the order;
  it reads two numbers and uses the general formula below.

Scoring:
  Let P = participant makespan computed by the checker. Ratio in [0,1] is:
    if (B <= T): ratio = (P <= T) ? 1 : 0;
    else        ratio = clamp( (B - P) / (B - T), 0, 1 ).
  With T = 0 and B > 0, this simplifies to ratio = clamp(1 - P/B, 0, 1).
  The checker emits partials via quitp(ratio, "... Ratio: <value>").
*/

struct Instance {
    int J, M;
    vector<vector<int>> m_of;
    vector<vector<long long>> p_of;
    vector<vector<int>> pos;  // pos[j][m] = k in job j
};

Instance read_instance(InStream& inf) {
    Instance I;
    I.J = inf.readInt(); I.M = inf.readInt();
    if (I.J <= 0 || I.M <= 0) quitf(_fail, "Invalid J or M");
    I.m_of.assign(I.J, vector<int>(I.M, -1));
    I.p_of.assign(I.J, vector<long long>(I.M, 0));
    vector<vector<int>> seen(I.J, vector<int>(I.M, 0));
    for (int j = 0; j < I.J; ++j) {
        for (int k = 0; k < I.M; ++k) {
            int m = inf.readInt();
            long long p = inf.readLong();
            if (m < 0 || m >= I.M) quitf(_fail, "Machine index out of range at job %d op %d", j, k);
            if (p <= 0) quitf(_fail, "Nonpositive processing time at job %d op %d", j, k);
            if (seen[j][m]) quitf(_fail, "Job %d uses machine %d more than once", j, m);
            seen[j][m] = 1;
            I.m_of[j][k] = m;
            I.p_of[j][k] = p;
        }
    }
    for (int j = 0; j < I.J; ++j) for (int m = 0; m < I.M; ++m) if (!seen[j][m]) quitf(_fail, "Job %d never uses machine %d", j, m);
    I.pos.assign(I.J, vector<int>(I.M, -1));
    for (int j = 0; j < I.J; ++j) for (int k = 0; k < I.M; ++k) I.pos[j][ I.m_of[j][k] ] = k;
    return I;
}

vector<vector<int>> read_solution(InStream& ouf, const Instance& I) {
    vector<vector<int>> seq(I.M, vector<int>(I.J, -1));
    for (int m = 0; m < I.M; ++m) {
        vector<int> seen(I.J, 0);
        for (int i = 0; i < I.J; ++i) {
            int x = ouf.readInt();
            if (x < 0 || x >= I.J) quitf(_wa, "Invalid job index %d at machine %d position %d", x, m, i);
            if (seen[x]) quitf(_wa, "Duplicate job %d on machine %d", x, m);
            seen[x] = 1;
            seq[m][i] = x;
        }
        for (int j = 0; j < I.J; ++j) if (!seen[j]) quitf(_wa, "Missing job %d on machine %d", j, m);
    }
    // If there are any extra tokens beyond the expected M*J integers, that's a WA.
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output after expected %d integers", I.J * I.M);
    }
    return seq;
}

long long compute_makespan(const Instance& I, const vector<vector<int>>& seq) {
    int J = I.J, M = I.M;
    long long N = 1LL*J*M;
    auto nid = [&](int j,int k){ return 1LL*j*M + k; };
    vector<vector<long long>> adj(N);
    vector<int> indeg(N, 0);
    vector<long long> w(N, 0);
    for (int j=0;j<J;++j){
        for (int k=0;k<M;++k){
            w[nid(j,k)] = I.p_of[j][k];
            if (k+1<M){ long long u=nid(j,k), v=nid(j,k+1); adj[u].push_back(v); indeg[v]++; }
        }
    }
    for (int m=0;m<M;++m){
        for (int i=0;i+1<J;++i){
            int j1=seq[m][i], j2=seq[m][i+1];
            int k1=I.pos[j1][m], k2=I.pos[j2][m];
            long long u=nid(j1,k1), v=nid(j2,k2);
            adj[u].push_back(v); indeg[v]++;
        }
    }
    deque<long long> dq;
    vector<long long> dist(N, 0);
    for (long long u=0;u<N;++u) if (indeg[u]==0){ dist[u]=w[u]; dq.push_back(u); }
    long long cnt=0;
    while(!dq.empty()){
        long long u=dq.front(); dq.pop_front(); cnt++;
        long long du=dist[u];
        for (long long v: adj[u]){
            if (dist[v] < du + w[v]) dist[v]=du + w[v];
            if (--indeg[v]==0) dq.push_back(v);
        }
    }
    if (cnt!=N) quitf(_wa, "Provided machine sequences induce a cycle; schedule invalid");
    long long C=0; for (long long u=0;u<N;++u) if (dist[u]>C) C=dist[u];
    return C;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    Instance I = read_instance(inf);
    auto seq = read_solution(ouf, I);
    long long a = ans.readLong();
    long long b = ans.readLong();
    long long B = max(a,b), T = min(a,b); // order-agnostic
    long long P = compute_makespan(I, seq);
    double ratio = 0.0, unbounded_ratio = 0.0;
    if (B <= T) ratio = (P <= T) ? 1.0 : 0.0;
    else {
        ratio = double(B - P) / double(B - T);
        unbounded_ratio = std::max(0.0, ratio);
        if (ratio < 0.0) ratio = 0.0;
        if (ratio > 1.0) ratio = 1.0;
    }
    quitp(ratio, "Makespan: %lld. Baseline: %lld. Best: %lld. Ratio: %.6f, RatioUnbounded: %.6f", P, B, T, ratio, unbounded_ratio);
}
