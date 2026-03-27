#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <set>
#include <cmath>
#include <algorithm>
using namespace std;

static inline string trim_str(const string &s) {
    size_t l = 0, r = s.size();
    while (l < r && isspace((unsigned char)s[l])) l++;
    while (r > l && isspace((unsigned char)s[r - 1])) r--;
    return s.substr(l, r - l);
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read n and teleporter array from input
    int n = inf.readInt();
    vector<int> a(n + 1);
    for (int i = 1; i <= n; i++) {
        a[i] = inf.readInt();
    }
    
    // Compute the correct answer: all rooms that can reach the same cycle as room 1
    // First, find the cycle that room 1 reaches
    vector<int> path;
    vector<bool> visited(n + 1, false);
    int cur = 1;
    while (!visited[cur]) {
        visited[cur] = true;
        path.push_back(cur);
        cur = a[cur];
    }
    
    // cur is now the start of the cycle
    set<int> cycle_rooms;
    bool in_cycle = false;
    for (int room : path) {
        if (room == cur) in_cycle = true;
        if (in_cycle) cycle_rooms.insert(room);
    }
    
    // The answer set A: all rooms that eventually reach this cycle
    set<int> answer_set;
    for (int start = 1; start <= n; start++) {
        int pos = start;
        for (int step = 0; step <= n; step++) {
            if (cycle_rooms.count(pos)) {
                answer_set.insert(start);
                break;
            }
            pos = a[pos];
        }
    }
    
    // Send n to contestant
    cout << n << endl;
    cout.flush();
    
    double total_cost = 0.0;
    
    // Process queries
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
        
        if (line[0] == '?') {
            // Query: ? u k |S| S1 S2 ... S|S|
            istringstream iss(line.substr(1));
            int u;
            long long k;
            int s_size;
            
            if (!(iss >> u >> k >> s_size)) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid query format");
            }
            
            if (u < 1 || u > n) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid u: %d", u);
            }
            
            if (k < 1) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid k: %lld", k);
            }
            
            if (s_size < 0 || s_size > n) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid |S|: %d", s_size);
            }
            
            set<int> S;
            for (int i = 0; i < s_size; i++) {
                int x;
                if (!(iss >> x)) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Not enough elements in S");
                }
                if (x < 1 || x > n) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Invalid element in S: %d", x);
                }
                if (S.count(x)) {
                    cout << -1 << endl;
                    cout.flush();
                    quitf(_wa, "Duplicate element in S: %d", x);
                }
                S.insert(x);
            }
            
            // Calculate cost for this query: 5 + sqrt(|S|) + log10(k)
            double query_cost = 5.0 + sqrt((double)s_size) + log10((double)k);
            total_cost += query_cost;
            
            // Simulate k teleports from u
            // Use cycle detection for large k
            int pos = u;
            
            // First, find the cycle starting from u
            vector<int> u_path;
            vector<int> u_pos(n + 1, -1);
            while (u_pos[pos] == -1) {
                u_pos[pos] = u_path.size();
                u_path.push_back(pos);
                pos = a[pos];
            }
            
            int cycle_start_idx = u_pos[pos];
            int cycle_len = u_path.size() - cycle_start_idx;
            
            // Determine final position after k steps
            int final_pos;
            if (k < (long long)u_path.size()) {
                final_pos = u_path[k];
            } else {
                long long remaining = (k - cycle_start_idx) % cycle_len;
                final_pos = u_path[cycle_start_idx + remaining];
            }
            
            int answer = S.count(final_pos) ? 1 : 0;
            cout << answer << endl;
            cout.flush();
            
        } else if (line[0] == '!') {
            // Answer: ! |A| A1 A2 ... A|A|
            istringstream iss(line.substr(1));
            int a_size;
            
            if (!(iss >> a_size)) {
                quitf(_wa, "Invalid answer format");
            }
            
            if (a_size < 0 || a_size > n) {
                quitf(_wa, "Invalid |A|: %d", a_size);
            }
            
            set<int> A;
            for (int i = 0; i < a_size; i++) {
                int x;
                if (!(iss >> x)) {
                    quitf(_wa, "Not enough elements in A");
                }
                if (x < 1 || x > n) {
                    quitf(_wa, "Invalid element in A: %d", x);
                }
                if (A.count(x)) {
                    quitf(_wa, "Duplicate element in A: %d", x);
                }
                A.insert(x);
            }
            
            // Check correctness
            if (A != answer_set) {
                quitf(_wa, "Wrong answer set. Expected size %d, got size %d", 
                      (int)answer_set.size(), (int)A.size());
            }
            
            // Scoring
            const double BEST_COST = 10000.0;
            const double WORST_COST = 150000.0;
            
            double score_ratio = max(0.0, min(1.0, (WORST_COST - total_cost) / (WORST_COST - BEST_COST)));
            double unbounded_ratio = max(0.0, (WORST_COST - total_cost) / (WORST_COST - BEST_COST));
            
            quitp(score_ratio, "Cost: %.2f. Ratio: %.4f, RatioUnbounded: %.4f",
                  total_cost, score_ratio, unbounded_ratio);
            
        } else {
            cout << -1 << endl;
            cout.flush();
            quitf(_wa, "Invalid command: %s", line.c_str());
        }
    }
    
    return 0;
}
