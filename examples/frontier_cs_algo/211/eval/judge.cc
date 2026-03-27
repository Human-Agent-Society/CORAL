#include "testlib.h"
#include <iostream>
#include <vector>
#include <set>
#include <map>
#include <algorithm>
#include <queue>
#include <cmath>
#include <climits>
#include <sstream>
#include <string>

using namespace std;

struct Entity {
    int id, x, y;
    char type;
};

struct Edge {
    int u, v;
    double cost;
    bool operator<(const Edge& other) const {
        return cost < other.cost;
    }
};

// Calculate distance cost between two entities
double dist_cost(int x1, int y1, int x2, int y2, char t1, char t2) {
    long long dx = (long long)x1 - x2;
    long long dy = (long long)y1 - y2;
    double r = (double)(dx * dx + dy * dy);
    
    string tc = "";
    tc += t1;
    tc += t2;
    
    if (tc == "RS" || tc == "SR" || tc == "SS") {
        return r * 0.8;
    }
    if (tc == "CC") {
        return 1e18; // Infinity - not allowed
    }
    return r;
}

// Union-Find (DSU) for MST
class DSU {
public:
    vector<int> parent;
    
    DSU(int n) {
        parent.resize(n);
        for (int i = 0; i < n; i++) {
            parent[i] = i;
        }
    }
    
    int find(int u) {
        if (parent[u] != u) {
            parent[u] = find(parent[u]);
        }
        return parent[u];
    }
    
    void merge(int u, int v) {
        int a = find(u), b = find(v);
        if (a != b) {
            parent[a] = b;
        }
    }
};

// Calculate MST cost for non-relay nodes only
double base_mst(const vector<Entity>& entities) {
    int n = entities.size();
    vector<Edge> edges;
    
    // Build edges between non-relay nodes only
    for (int i = 0; i < n; i++) {
        if (entities[i].type == 'C') continue;
        for (int j = i + 1; j < n; j++) {
            if (entities[j].type == 'C') continue;
            double cost = dist_cost(
                entities[i].x, entities[i].y,
                entities[j].x, entities[j].y,
                entities[i].type, entities[j].type
            );
            edges.push_back({i, j, cost});
        }
    }
    
    sort(edges.begin(), edges.end());
    
    DSU dsu(n);
    double total_cost = 0.0;
    int cnt = 0;
    
    for (const auto& e : edges) {
        if (dsu.find(e.u) != dsu.find(e.v)) {
            dsu.merge(e.u, e.v);
            total_cost += e.cost;
            cnt++;
        }
    }
    
    return total_cost;
}

// Calculate actual network cost
double fitness(const set<int>& relay_nodes, const vector<pair<int, int> >& edges, 
               const vector<Entity>& entities) {
    map<int, int> id_to_idx;
    for (size_t i = 0; i < entities.size(); i++) {
        id_to_idx[entities[i].id] = i;
    }
    
    double total_cost = 0.0;
    for (const auto& e : edges) {
        // These should have been verified in verify(), but check for safety
        if (id_to_idx.find(e.first) == id_to_idx.end() || 
            id_to_idx.find(e.second) == id_to_idx.end()) {
            return 1e18; // Invalid edge
        }
        int idx1 = id_to_idx[e.first];
        int idx2 = id_to_idx[e.second];
        double cost = dist_cost(
            entities[idx1].x, entities[idx1].y,
            entities[idx2].x, entities[idx2].y,
            entities[idx1].type, entities[idx2].type
        );
        total_cost += cost;
    }
    
    return total_cost;
}

// Verify solution validity
bool verify(const set<int>& relay_nodes, const vector<pair<int, int> >& edges,
            const vector<Entity>& entities) {
    set<int> ids;
    set<int> relay_ids;
    
    for (const auto& e : entities) {
        if (e.type == 'C') {
            relay_ids.insert(e.id);
        }
        ids.insert(e.id);
    }
    
    // Check relay_nodes are valid relay nodes
    set<int> dup_ids;
    for (int id : relay_nodes) {
        if (relay_ids.find(id) == relay_ids.end()) {
            return false;
        }
        if (dup_ids.find(id) != dup_ids.end()) {
            return false;
        }
        dup_ids.insert(id);
    }
    
    // Check edges
    for (const auto& e : edges) {
        if (e.first == e.second) {
            return false;
        }
        if (ids.find(e.first) == ids.end() || ids.find(e.second) == ids.end()) {
            return false;
        }
        // Cannot connect two relay nodes
        if (relay_ids.find(e.first) != relay_ids.end() && 
            relay_ids.find(e.second) != relay_ids.end()) {
            return false;
        }
    }
    
    // Check connectivity using DSU
    map<int, int> id_to_idx;
    for (size_t i = 0; i < entities.size(); i++) {
        id_to_idx[entities[i].id] = i;
    }
    
    int m = entities.size();
    DSU dsu(m);
    for (const auto& e : edges) {
        int idx1 = id_to_idx[e.first];
        int idx2 = id_to_idx[e.second];
        dsu.merge(idx1, idx2);
    }
    
    if (m > 0) {
        // All non-relay nodes must be connected
        // Find first non-relay node as reference
        int ref_idx = -1;
        for (size_t i = 0; i < entities.size(); i++) {
            if (entities[i].type != 'C') {
                ref_idx = i;
                break;
            }
        }
        if (ref_idx == -1) {
            // No non-relay nodes, which is invalid
            return false;
        }
        int same = dsu.find(ref_idx);
        for (size_t i = 0; i < entities.size(); i++) {
            if (entities[i].type == 'C') continue;
            if (dsu.find(i) != same) {
                return false;
            }
        }
    }
    
    return true;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input
    int n = inf.readInt();  // Number of robots
    int k = inf.readInt();  // Number of optional relays
    
    vector<Entity> entities;
    for (int i = 0; i < n + k; i++) {
        int id = inf.readInt();
        int x = inf.readInt();
        int y = inf.readInt();
        string type_str = inf.readToken();
        char type = type_str[0];
        entities.push_back({id, x, y, type});
    }
    
    // Read output - first line: relay nodes
    string relay_line = ouf.readLine();
    if (relay_line.empty()) {
        quitf(_wa, "Empty relay nodes line");
    }
    // Remove trailing whitespace
    while (!relay_line.empty() && (relay_line.back() == '\r' || relay_line.back() == '\n' || relay_line.back() == ' ' || relay_line.back() == '\t')) {
        relay_line.pop_back();
    }
    set<int> relay_nodes;
    if (relay_line != "#" && !relay_line.empty()) {
        // Parse relay nodes separated by '#'
        stringstream ss(relay_line);
        string token;
        while (getline(ss, token, '#')) {
            // Remove whitespace from token
            size_t first = token.find_first_not_of(" \t\r\n");
            if (first != string::npos) {
                token = token.substr(first);
            }
            size_t last = token.find_last_not_of(" \t\r\n");
            if (last != string::npos) {
                token = token.substr(0, last + 1);
            } else {
                token.clear();
            }
            if (!token.empty()) {
                int id = atoi(token.c_str());
                if (id <= 0) {
                    quitf(_wa, "Invalid relay node ID: %s", token.c_str());
                }
                relay_nodes.insert(id);
            }
        }
    }
    
    // Read output - second line: edges
    string edge_line = ouf.readLine();
    // Remove trailing whitespace
    while (!edge_line.empty() && (edge_line.back() == '\r' || edge_line.back() == '\n' || edge_line.back() == ' ' || edge_line.back() == '\t')) {
        edge_line.pop_back();
    }
    vector<pair<int, int> > edges;
    if (edge_line != "#" && !edge_line.empty()) {
        // Parse edges separated by '#', each edge is "id1-id2"
        stringstream ss(edge_line);
        string token;
        while (getline(ss, token, '#')) {
            // Remove whitespace from token
            size_t first = token.find_first_not_of(" \t\r\n");
            if (first != string::npos) {
                token = token.substr(first);
            }
            size_t last = token.find_last_not_of(" \t\r\n");
            if (last != string::npos) {
                token = token.substr(0, last + 1);
            } else {
                token.clear();
            }
            if (!token.empty()) {
                size_t pos = token.find('-');
                if (pos == string::npos || pos == 0 || pos == token.length() - 1) {
                    quitf(_wa, "Invalid edge format: %s", token.c_str());
                }
                int id1 = atoi(token.substr(0, pos).c_str());
                int id2 = atoi(token.substr(pos + 1).c_str());
                if (id1 <= 0 || id2 <= 0) {
                    quitf(_wa, "Invalid edge node ID in: %s", token.c_str());
                }
                edges.push_back({id1, id2});
            }
        }
    }
    
    // Verify solution
    if (!verify(relay_nodes, edges, entities)) {
        quitf(_wa, "Invalid solution: relay nodes or edges are not valid, or network is not connected");
    }
    double d = base_mst(entities);
    // Calculate base MST cost (without relays)
    double base_cost = d/9*8;
    double zero_cost = d;
    
    // Calculate actual network cost
    double actual_cost = fitness(relay_nodes, edges, entities);
    
    // Handle edge cases
    if (actual_cost >= 1e17 || actual_cost -1e-6 <0) {
        quitf(_wa, "Invalid solution: contains invalid edges");
    }
    
    // Calculate score ratio
    // Score = base_cost / actual_cost
    // If actual_cost <= base_cost, we get full score (1.0)
    // If actual_cost > base_cost, score decreases
    double score_ratio;
    if (actual_cost <= base_cost) {
        score_ratio = 1.0;  // Perfect or better solution
    } else if (actual_cost >= zero_cost) {
        score_ratio = 0.0;
    } else {
        score_ratio = min(1.0, (zero_cost-actual_cost) / (zero_cost-base_cost));
    }
    
    // Ensure score is non-negative
    score_ratio = max(0.0, score_ratio);
    double unbounded_ratio = score_ratio;
    
    quitp(score_ratio, "Value: %.4f. Ratio: %.4f, RatioUnbounded: %.4f", actual_cost, score_ratio, unbounded_ratio);
    
    return 0;
}

