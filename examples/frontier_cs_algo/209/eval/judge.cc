#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static inline string trim_str(const string &s) {
    size_t l = 0, r = s.size();
    while (l < r && isspace((unsigned char)s[l])) l++;
    while (r > l && isspace((unsigned char)s[r - 1])) r--;
    return s.substr(l, r - l);
}

int h, n;
vector<long long> f;
vector<vector<long long>> prefix_sum;
vector<int> query_count_per_u;  // 每个 u 的查询次数

inline int get_depth(int x) {
    return 31 - __builtin_clz(x);
}

inline int first_at_depth(int d) {
    return 1 << d;
}

inline int last_at_depth(int d) {
    return (1 << (d + 1)) - 1;
}

void preprocess() {
    prefix_sum.resize(h);
    for (int d = 0; d < h; d++) {
        int start = first_at_depth(d);
        int end = min(last_at_depth(d), n);
        int cnt = end - start + 1;
        prefix_sum[d].resize(cnt + 1, 0);
        for (int i = 0; i < cnt; i++) {
            prefix_sum[d][i + 1] = prefix_sum[d][i] + f[start + i];
        }
    }
}

long long subtree_sum_at_depth(int node, int target_depth) {
    if (node < 1 || node > n) return 0;
    int d = get_depth(node);
    if (d > target_depth || target_depth >= h) return 0;
    if (d == target_depth) return f[node];
    
    int steps = target_depth - d;
    int left = node << steps;
    int right = ((node + 1) << steps) - 1;
    
    int depth_start = first_at_depth(target_depth);
    int depth_end = min(last_at_depth(target_depth), n);
    
    left = max(left, depth_start);
    right = min(right, depth_end);
    
    if (left > right) return 0;
    
    int left_idx = left - depth_start;
    int right_idx = right - depth_start;
    return prefix_sum[target_depth][right_idx + 1] - prefix_sum[target_depth][left_idx];
}

long long query_sum(int center, int dist) {
    if (dist <= 0) return 0;
    
    long long result = 0;
    int center_depth = get_depth(center);
    
    result += subtree_sum_at_depth(center, center_depth + dist);
    
    int cur = center;
    for (int k = 1; k <= dist && k <= center_depth; k++) {
        int prev = cur;
        cur = cur / 2;
        int other_child = (prev == cur * 2) ? (cur * 2 + 1) : (cur * 2);
        
        int remaining = dist - k;
        if (remaining == 0) {
            result += f[cur];
        } else if (other_child <= n) {
            result += subtree_sum_at_depth(other_child, get_depth(other_child) + remaining - 1);
        }
    }
    
    return result;
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    h = inf.readInt();
    n = (1 << h) - 1;

    vector<int> p(n + 1);
    for (int i = 1; i <= n; i++) {
        p[i] = inf.readInt();
    }

    f.resize(n + 1);
    for (int i = 1; i <= n; i++) {
        f[i] = inf.readLong();
    }

    preprocess();

    long long total_sum = 0;
    for (int i = 1; i <= n; i++) {
        total_sum += f[i];
    }

    // 初始化每个 u 的查询计数
    query_count_per_u.resize(n + 1, 0);

    // L = 3 * n / 4, R = (13 * n + 21) / 8
    long long L = 3LL * n / 4;
    long long R = (13LL * n + 21) / 8;

    cout << h << endl;
    cout.flush();

    int query_count = 0;
    const int MAX_QUERIES_PER_U = 5;        // 每个 u 的查询次数限制

    while (true) {
        string line;
        do {
            line = ouf.readLine();
            line = trim_str(line);
        } while (line.empty() || line[0] == '#');

        if (line[0] == '!') {
            istringstream iss(line.substr(1));
            long long user_ans;
            if (!(iss >> user_ans)) {
                quitf(_wa, "Invalid answer format");
            }
            
            if (user_ans != total_sum) {
                quitf(_wa, "Wrong answer: expected %lld, got %lld", total_sum, user_ans);
            }
            
            // 超过 R 则 0 分，低于 L 则满分，中间线性插值
            double score_ratio = max(0.0, min(1.0, (double)(R - query_count) / (double)(R - L)));
            double unbounded_ratio = max(0.0, (double)(R - query_count) / (double)(R - L));
            
            quitp(score_ratio, "Queries: %d. Ratio: %.4f, RatioUnbounded: %.4f", 
                  query_count, score_ratio, unbounded_ratio);
            return 0;
        } else if (line[0] == '?') {
            istringstream iss(line.substr(1));
            int u;
            long long d;
            if (!(iss >> u >> d)) {
                quitf(_wa, "Invalid query format: %s", line.c_str());
            }
            
            if (u < 1 || u > n) {
                quitf(_wa, "Invalid u: %d (should be 1 <= u <= %d)", u, n);
            }
            if (d < 1) {
                quitf(_wa, "Invalid d: %lld (should be d >= 1)", d);
            }
            
            // 检查每个 u 的查询次数限制
            query_count_per_u[u]++;
            if (query_count_per_u[u] > MAX_QUERIES_PER_U) {
                quitf(_wa, "Too many queries on u = %d (exceeded %d)", u, MAX_QUERIES_PER_U);
            }
            
            query_count++;
            
            int center = p[u];
            long long result = query_sum(center, (int)d);
            
            cout << result << endl;
            cout.flush();
        } else {
            quitf(_wa, "Invalid command: %s", line.c_str());
        }
    }
    
    return 0;
}
