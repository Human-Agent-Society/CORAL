#include "testlib.h"
#include <vector>
#include <string>
#include <cmath>

namespace {
    constexpr int MAX_N = (int)1E5 + 10, SINGLE_QUERY_LIM = (int)1E7,
                  TOTAL_ROUND_LIM = (int)1E7, TOTAL_QUERY_LIM = (int)3E8;
    int subtask, n;
    int cnt_query, cnt_round;
    int inter[SINGLE_QUERY_LIM+10];
    
    // Helper to ensure conditions and quit if they fail
    void Ensure(bool condition, const char* fail_message) {
        if (!condition){
            quitf(_wa, fail_message);
        }
    }

    int p[MAX_N], q[MAX_N], vis[MAX_N], an;
    
    int flip(int u) {
        u = q[u];
        if (vis[u] ^= 1) {
            an += vis[u - 1] + vis[u + 1];
        } else {
            an -= vis[u - 1] + vis[u + 1];
        }
        return an || (vis[1] && vis[n]);
    }
    
    bool check(int c1[], int c2[]) {
        int opt = -1;
        for (int i = 0; i < n; i++)
            if (c1[i] == c2[0]) {
                opt = i;
                break;
            }
        if (opt == -1) return false;
        
        bool f1 = true, f2 = true;
        for (int i = 1, op1 = opt, op2 = opt; i < n; i++) {
            op1++; op2--;
            if (op1 >= n) op1 -= n;
            if (op2 < 0) op2 += n;
            if (c1[op1] != c2[i]) f1 = false;
            if (c1[op2] != c2[i]) f2 = false;
            if ((!f1) && (!f2)) return false;
        }
        return true;
    }

    double f(double x) {
        return std::min(std::max(std::log2(x), 0.0), 8.0);
    }
    
    double lambda(int t, int Q) {
        return std::max(0.0, 1 - 0.1 * (f(t / 18.0) + f(Q / 1.5E7)));
    }

} // namespace

void input_inter(int N){
    for(int i = 0; i < N; i++)
        inter[i] = ouf.readInt();
}

void output_inter(const int N){
    std::vector<int> temp_vec;
    for (int i=0; i<N; ++i) temp_vec.push_back(inter[i]);
    println(temp_vec);
}

void query(const int N) {
    for (int i = 0; i < N; i++) {
        int u = inter[i];
        Ensure(1 <= u && u <= n, "Query value out of range [1, n]");
        inter[i] = flip(u);
    }
    output_inter(N);
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    subtask = inf.readInt();
    n = inf.readInt();
    for (int i = 0; i < n; i++) {
        p[i] = ans.readInt();
        q[p[i]] = i + 1;
    }

    inter[0] = subtask;
    inter[1] = n;
    output_inter(2);
    
    int N;
    while (true) {
        N = ouf.readInt();
        if (N == -1) {
            input_inter(n);
            Ensure(check(p, inter), "Final answer is incorrect.");
            break;
        } else {
            Ensure(N <= SINGLE_QUERY_LIM, "Single query size limit exceeded.");
            cnt_round += 1;
            cnt_query += N;
            Ensure(cnt_round <= TOTAL_ROUND_LIM, "Total round limit exceeded.");
            Ensure(cnt_query <= TOTAL_QUERY_LIM, "Total query limit exceeded.");
            input_inter(N);
            query(N);
        }
    }
    
    double score_ratio = lambda(cnt_round, cnt_query);
    
    // Use quitp with a formatted message that includes the "Ratio:" tag
    quitp(score_ratio, "Correct. Rounds: %d, Queries: %d. Ratio: %.4f", cnt_round, cnt_query, score_ratio);
    
    return 0;
}

