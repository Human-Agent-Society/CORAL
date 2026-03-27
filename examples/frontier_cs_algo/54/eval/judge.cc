#include "testlib.h"
#include <vector>
#include <iostream>
#include <algorithm>
#include <cmath>
#include <iomanip>

using namespace std;


const int LIMIT_BASE = 100000;
const int LIMIT_ZERO = 400000;

const int MAXN = 80005;
const int LOGK = 18;

vector<int> adj[MAXN];
int up[LOGK][MAXN];
int depth[MAXN];
int queries = 0;

void dfs(int u, int p, int d) {
    depth[u] = d;
    up[0][u] = p;
    for (int v : adj[u]) {
        if (v != p) {
            dfs(v, u, d + 1);
        }
    }
}

void precompute_lca(int n) {
    dfs(1, 1, 0);
    for (int k = 1; k < LOGK; ++k) {
        for (int i = 1; i <= n; ++i) {
            up[k][i] = up[k - 1][up[k - 1][i]];
        }
    }
}

int get_lca(int u, int v) {
    if (depth[u] < depth[v]) swap(u, v);
    for (int k = LOGK - 1; k >= 0; --k) {
        if (depth[u] - (1 << k) >= depth[v]) {
            u = up[k][u];
        }
    }
    if (u == v) return u;
    for (int k = LOGK - 1; k >= 0; --k) {
        if (up[k][u] != up[k][v]) {
            u = up[k][u];
            v = up[k][v];
        }
    }
    return up[0][u];
}

int get_dist(int u, int v) {
    return depth[u] + depth[v] - 2 * depth[get_lca(u, v)];
}

int main(int argc, char* argv[]) {
    setName("Interactor for Centroid Guess with Bounded/Unbounded Scoring");
    registerInteraction(argc, argv);

    int n = inf.readInt(3, 75000, "n");
    
    for (int i = 0; i < n - 1; ++i) {
        int u = inf.readInt(1, n, "u");
        int v = inf.readInt(1, n, "v");
        adj[u].push_back(v);
        adj[v].push_back(u);
    }

    int expected_centroid = ans.readInt(1, n, "centroid");

    precompute_lca(n);

    cout << n << endl;

    int safety_limit = LIMIT_ZERO + 10000; 
    bool solved = false;

    while (!solved) {
        string type = ouf.readToken("[?!]");

        if (type == "?") {
            queries++;
            if (queries > safety_limit) {
                quitf(_wa, "Safety query limit exceeded (> %d)", safety_limit);
            }

            int u = ouf.readInt(1, n, "query_u");
            int v = ouf.readInt(1, n, "query_v");
            
            int dist = get_dist(u, v);
            cout << dist << endl;
        } 
        else if (type == "!") {
            int user_ans = ouf.readInt(1, n, "user_answer");

            if (user_ans == expected_centroid) {
                solved = true;
            } else {
                quitf(_wa, "Wrong answer. Expected %d, found %d.", expected_centroid, user_ans);
            }
        }
    }

    double L = (double)LIMIT_ZERO;
    double O = (double)LIMIT_BASE;
    
    double bounded_score = 0.0;
    
    if (queries <= LIMIT_BASE) {
        bounded_score = 1.0;
    } else if (queries >= LIMIT_ZERO) {
        bounded_score = 0.0;
    } else {
        double ratio = (L - queries) / (L - O);
        bounded_score = ratio * ratio;
    }

    double ratio_unbounded = max(0.0, (L - queries) / (L - O));
    double unbounded_score = ratio_unbounded * ratio_unbounded;

    quitp(bounded_score, 
          "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", 
          queries, bounded_score, unbounded_score);

    return 0;
}
