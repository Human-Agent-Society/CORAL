#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <set>
#include <cmath>
#include <algorithm>
#include <queue>
using namespace std;

static inline string trim_str(const string &s) {
    size_t l = 0, r = s.size();
    while (l < r && isspace((unsigned char)s[l])) l++;
    while (r > l && isspace((unsigned char)s[r - 1])) r--;
    return s.substr(l, r - l);
}

// Union-Find for connectivity
class DSU {
public:
    vector<int> parent, rank_;
    DSU(int n) : parent(n + 1), rank_(n + 1, 0) {
        for (int i = 0; i <= n; i++) parent[i] = i;
    }
    int find(int x) {
        if (parent[x] != x) parent[x] = find(parent[x]);
        return parent[x];
    }
    void unite(int x, int y) {
        int rx = find(x), ry = find(y);
        if (rx == ry) return;
        if (rank_[rx] < rank_[ry]) swap(rx, ry);
        parent[ry] = rx;
        if (rank_[rx] == rank_[ry]) rank_[rx]++;
    }
    bool connected(int x, int y) { return find(x) == find(y); }
};

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    int t = inf.readInt();
    
    // Store all test case data
    vector<int> all_n(t), all_m(t);
    vector<vector<pair<int,int>>> all_edges(t);
    vector<vector<int>> all_repaired(t); // which roads are repaired
    
    for (int tc = 0; tc < t; tc++) {
        int n = inf.readInt();
        int m = inf.readInt();
        all_n[tc] = n;
        all_m[tc] = m;
        
        all_edges[tc].resize(m);
        for (int i = 0; i < m; i++) {
            int a = inf.readInt();
            int b = inf.readInt();
            all_edges[tc][i] = {a, b};
        }
        
        // Read repaired roads (1 = repaired, 0 = not)
        all_repaired[tc].resize(m);
        for (int i = 0; i < m; i++) {
            all_repaired[tc][i] = inf.readInt();
        }
    }
    
    // Send t to contestant
    cout << t << endl;
    cout.flush();
    
    double total_cost = 0.0;
    
    for (int tc = 0; tc < t; tc++) {
        int n = all_n[tc];
        int m = all_m[tc];
        auto& edges = all_edges[tc];
        auto& repaired = all_repaired[tc];
        
        // Send n, m
        cout << n << " " << m << endl;
        // Send edges
        for (int i = 0; i < m; i++) {
            cout << edges[i].first << " " << edges[i].second << endl;
        }
        cout.flush();
        
        // Track blocked roads
        vector<bool> blocked(m, false);
        int request_count = 0;
        int max_requests = 100 * m;
        
        // Process requests for this test case
        while (true) {
            string line;
            do {
                if (!ouf.seekEof()) {
                    line = ouf.readLine();
                    line = trim_str(line);
                } else {
                    quitf(_wa, "Unexpected EOF");
                }
            } while (line.empty());
            
            if (line[0] == '-') {
                // Block road: - x
                request_count++;
                if (request_count > max_requests) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Too many requests");
                }
                
                istringstream iss(line.substr(1));
                int x;
                if (!(iss >> x) || x < 1 || x > m) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Invalid block request");
                }
                
                blocked[x - 1] = true;
                total_cost += 2.0;
                
            } else if (line[0] == '+') {
                // Unblock road: + x
                request_count++;
                if (request_count > max_requests) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Too many requests");
                }
                
                istringstream iss(line.substr(1));
                int x;
                if (!(iss >> x) || x < 1 || x > m) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Invalid unblock request");
                }
                
                if (!blocked[x - 1]) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Unblocking non-blocked road %d", x);
                }
                
                blocked[x - 1] = false;
                total_cost += 2.0;
                
            } else if (line[0] == '?') {
                // Query: ? k y1 y2 ... yk
                request_count++;
                if (request_count > max_requests) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Too many requests");
                }
                
                istringstream iss(line.substr(1));
                int k;
                if (!(iss >> k) || k < 1 || k > n) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Invalid query k");
                }
                
                vector<int> ys(k);
                for (int i = 0; i < k; i++) {
                    if (!(iss >> ys[i]) || ys[i] < 1 || ys[i] > n) {
                        cout << -1 << endl;
                        cout.flush();
                        quitf(_wa, "Invalid query point");
                    }
                }
                
                // Cost: 0.5 + log2(k + 1)
                total_cost += 0.5 + log2((double)(k + 1));
                
                // Build connectivity using repaired AND unblocked roads
                DSU dsu(n);
                for (int i = 0; i < m; i++) {
                    if (repaired[i] && !blocked[i]) {
                        dsu.unite(edges[i].first, edges[i].second);
                    }
                }
                
                // Randomly select Y from ys
                int Y = ys[rnd.next(0, k - 1)];
                
                // Select starting point s adversarially
                // For adaptive behavior: choose s to minimize information given
                // Simple strategy: check if all ys are in same component
                // If so, return 1; otherwise, choose s from a different component
                
                // Find all components
                set<int> y_components;
                for (int y : ys) {
                    y_components.insert(dsu.find(y));
                }
                
                // Choose s: if possible, from a component not containing any y
                // Otherwise, from the component of Y
                int s = Y; // default
                for (int node = 1; node <= n; node++) {
                    int comp = dsu.find(node);
                    if (y_components.find(comp) == y_components.end()) {
                        s = node;
                        break;
                    }
                }
                
                // Return reachability from s to Y
                int result = dsu.connected(s, Y) ? 1 : 0;
                cout << result << endl;
                cout.flush();
                
            } else if (line[0] == '!') {
                // Answer: ! c1 c2 ... cm
                istringstream iss(line.substr(1));
                vector<int> answer(m);
                for (int i = 0; i < m; i++) {
                    if (!(iss >> answer[i])) {
                        cout << 0 << endl;
                        cout.flush();
                        quitf(_wa, "Invalid answer format");
                    }
                }
                
                // Check answer
                bool correct = true;
                for (int i = 0; i < m; i++) {
                    if (answer[i] != repaired[i]) {
                        correct = false;
                        break;
                    }
                }
                
                if (!correct) {
                    cout << 0 << endl;
                    cout.flush();
                    quitf(_wa, "Wrong answer for test case %d", tc + 1);
                }
                
                cout << 1 << endl;
                cout.flush();
                break; // Move to next test case
                
            } else {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid command: %s", line.c_str());
            }
        }
    }
    
    // Scoring
    const double BEST_COST = 50000.0;
    const double WORST_COST = 150000.0;
    
    double score_ratio = max(0.0, min(1.0, (WORST_COST - total_cost) / (WORST_COST - BEST_COST)));
    double unbounded_ratio = max(0.0, (WORST_COST - total_cost) / (WORST_COST - BEST_COST));
    
    quitp(score_ratio, "Cost: %.2f. Ratio: %.4f, RatioUnbounded: %.4f",
          total_cost, score_ratio, unbounded_ratio);
    
    return 0;
}
