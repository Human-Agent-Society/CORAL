#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <set>
#include <map>
#include <queue>
#include <sstream>
#include <functional>
#include <algorithm>
using namespace std;

static const int MAXN = 1010;

int n, m, T;
vector<int> adj[MAXN];
int outdeg[MAXN];
// state: 0 = Lose, 1 = Win, 2 = Draw, -1 = undetermined
int state[MAXN];
int nimber[MAXN];

// Build reverse graph - global to avoid stack overflow
vector<int> radj[MAXN];
int undecided[MAXN];

// For single token game state computation
// We use a simple approach: vertices with self-loops or in SCCs with size>1 are Draw
bool visited[MAXN];

// Compute Win/Lose/Draw state for single token on each vertex
void compute_states() {
    // First pass: mark Draw vertices (have self-loop)
    for (int i = 1; i <= n; i++) {
        state[i] = -1;
        for (int v : adj[i]) {
            if (v == i) {
                state[i] = 2; // Self-loop -> Draw
                break;
            }
        }
    }
    
    // Second pass: propagate Win/Lose states for non-Draw vertices
    queue<int> q;
    
    // Vertices with no outgoing edges (except self-loop) are Lose
    for (int i = 1; i <= n; i++) {
        if (state[i] != 2 && outdeg[i] == 0) {
            state[i] = 0; // Lose
            q.push(i);
        }
    }
    
    // Build reverse graph
    for (int i = 1; i <= n; i++) {
        radj[i].clear();
        undecided[i] = 0;
    }
    for (int u = 1; u <= n; u++) {
        for (int v : adj[u]) {
            if (u != v) {  // Skip self-loops
                radj[v].push_back(u);
                if (state[v] != 2) {
                    undecided[u]++;
                }
            }
        }
    }
    
    // BFS to propagate Win/Lose
    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int v : radj[u]) {
            if (state[v] != -1) continue;
            if (state[u] == 0) {
                // u is Lose, v can reach Lose -> v is Win
                state[v] = 1;
                q.push(v);
            } else if (state[u] == 1) {
                // u is Win, decrease undecided
                undecided[v]--;
                if (undecided[v] == 0) {
                    // All non-Draw successors are Win -> v is Lose
                    state[v] = 0;
                    q.push(v);
                }
            }
        }
    }
    
    // Remaining vertices: either Draw or Lose
    // If a vertex can only reach Draw vertices (or itself), it's also Draw
    for (int i = 1; i <= n; i++) {
        if (state[i] == -1) {
            // Check if all successors are Draw or undetermined
            bool all_draw = true;
            for (int v : adj[i]) {
                if (v != i && state[v] != 2 && state[v] != -1) {
                    all_draw = false;
                    break;
                }
            }
            if (all_draw && outdeg[i] > 0) {
                state[i] = 2; // Can reach Draw states -> Draw
            } else if (undecided[i] == 0 && outdeg[i] > 0) {
                state[i] = 2; // All successors determined non-losing -> Draw
            } else {
                state[i] = 0; // Default to Lose
            }
        }
    }
}

// Compute nimber (Sprague-Grundy value) for non-Draw vertices
// Using iterative approach with reverse topological sort to avoid stack overflow
void compute_nimbers() {
    for (int i = 1; i <= n; i++) {
        nimber[i] = -1;
    }
    
    // Count outgoing edges to non-Draw vertices
    int out_count[MAXN] = {0};
    for (int u = 1; u <= n; u++) {
        if (state[u] == 2) continue;
        for (int v : adj[u]) {
            if (state[v] != 2) {
                out_count[u]++;
            }
        }
    }
    
    // Start with sink vertices (no outgoing edges to non-Draw vertices)
    queue<int> q;
    for (int i = 1; i <= n; i++) {
        if (state[i] != 2 && out_count[i] == 0) {
            nimber[i] = 0; // Sink vertices have nimber 0
            q.push(i);
        }
    }
    
    // Process in reverse topological order
    while (!q.empty()) {
        int v = q.front(); q.pop();
        
        // Update all predecessors of v
        for (int u : radj[v]) {
            if (state[u] == 2) continue;
            out_count[u]--;
            
            // If all successors of u have been processed, compute nimber[u]
            if (out_count[u] == 0 && nimber[u] == -1) {
                set<int> mex_set;
                for (int w : adj[u]) {
                    if (state[w] == 2) continue;
                    if (nimber[w] >= 0) {
                        mex_set.insert(nimber[w]);
                    }
                }
                int mex = 0;
                while (mex_set.count(mex)) mex++;
                nimber[u] = mex;
                q.push(u);
            }
        }
    }
    
    // Handle any remaining vertices (shouldn't happen in a proper DAG)
    for (int i = 1; i <= n; i++) {
        if (state[i] != 2 && nimber[i] == -1) {
            nimber[i] = 0;
        }
    }
}

// Compute game result for a multiset of tokens
// Returns "Win", "Lose", or "Draw"
string compute_result(const vector<int>& tokens) {
    if (tokens.empty()) {
        // No tokens means first player cannot move -> Lose
        return "Lose";
    }
    
    // Separate Draw tokens and non-Draw tokens
    vector<int> draw_tokens;
    vector<int> nondraw_tokens;
    
    for (int v : tokens) {
        if (state[v] == 2) {
            draw_tokens.push_back(v);
        } else {
            nondraw_tokens.push_back(v);
        }
    }
    
    // Compute XOR of nimbers for non-Draw tokens
    int xor_val = 0;
    for (int v : nondraw_tokens) {
        if (nimber[v] >= 0) {
            xor_val ^= nimber[v];
        }
    }
    
    if (draw_tokens.empty()) {
        // Standard Sprague-Grundy: xor = 0 -> Lose, else Win
        if (xor_val == 0) return "Lose";
        else return "Win";
    }
    
    // Has Draw tokens - need careful analysis
    // For each Draw token, check if it can move to a position that makes XOR = 0
    // If any Draw token can do this, first player Wins
    
    for (int d : draw_tokens) {
        // Check all successors of d (excluding self-loop)
        for (int succ : adj[d]) {
            if (succ == d) continue; // Skip self-loop
            
            if (state[succ] == 2) {
                // Moving to another Draw state doesn't help immediately
                continue;
            }
            
            // If we move d's token to succ, the new XOR would be xor_val ^ nimber[succ]
            // If this equals 0, we Win
            if (nimber[succ] >= 0 && (xor_val ^ nimber[succ]) == 0) {
                return "Win";
            }
        }
    }
    
    // No Draw token can immediately make XOR = 0
    // Since Draw tokens have self-loops, player can always stall the game forever
    // The game becomes a Draw because:
    // - Player can keep moving on self-loop indefinitely
    // - Neither player is forced to lose
    return "Draw";
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    
    // Read input
    n = inf.readInt();
    m = inf.readInt();
    T = inf.readInt();
    
    for (int i = 0; i < m; i++) {
        int a = inf.readInt();
        int b = inf.readInt();
        adj[a].push_back(b);
        outdeg[a]++;
    }
    
    // Send initial graph to contestant
    cout << n << " " << m << " " << T << endl;
    for (int u = 1; u <= n; u++) {
        for (int v : adj[u]) {
            cout << u << " " << v << endl;
        }
    }
    cout.flush();
    
    // Read number of modifications
    int K = ouf.readInt(0, 10000000, "K");
    
    // Apply modifications
    set<pair<int,int>> edges;
    for (int u = 1; u <= n; u++) {
        for (int v : adj[u]) {
            edges.insert({u, v});
        }
    }
    
    for (int i = 0; i < K; i++) {
        string op = ouf.readToken();
        int a = ouf.readInt(1, n, "a");
        int b = ouf.readInt(1, n, "b");
        
        if (op == "+") {
            edges.insert({a, b});
        } else if (op == "-") {
            edges.erase({a, b});
        } else {
            quitf(_wa, "Invalid operation: %s", op.c_str());
        }
    }
    
    // Rebuild graph
    for (int i = 1; i <= n; i++) {
        adj[i].clear();
        outdeg[i] = 0;
    }
    for (auto& e : edges) {
        adj[e.first].push_back(e.second);
        outdeg[e.first]++;
    }
    
    // Compute states and nimbers
    compute_states();
    compute_nimbers();
    
    // Process T rounds
    int max_queries = 0;
    
    for (int round = 0; round < T; round++) {
        // Adaptive interactor: maintain set of possible hidden vertices
        set<int> possible;
        for (int i = 1; i <= n; i++) possible.insert(i);
        
        int queries_this_round = 0;
        
        while (true) {
            if (ouf.seekEof()) {
                quitf(_wa, "Unexpected end of output in round %d", round + 1);
            }
            
            string line;
            do {
                if (ouf.seekEof()) {
                    quitf(_wa, "Unexpected end of output in round %d", round + 1);
                }
                line = ouf.readLine();
                // trim
                while (!line.empty() && isspace(line.back())) line.pop_back();
                while (!line.empty() && isspace(line.front())) line.erase(line.begin());
            } while (line.empty());
            
            if (line[0] == '?') {
                // Query
                queries_this_round++;
                
                istringstream iss(line.substr(1));
                int s;
                iss >> s;
                vector<int> S(s);
                for (int i = 0; i < s; i++) {
                    iss >> S[i];
                    if (S[i] < 1 || S[i] > n) {
                        quitf(_wa, "Invalid vertex in query: %d", S[i]);
                    }
                }
                
                // For adaptive interactor: find an answer consistent with at least one possible v
                // Group possible vertices by their answer
                map<string, vector<int>> by_answer;
                for (int v : possible) {
                    vector<int> tokens = S;
                    tokens.push_back(v);
                    string res = compute_result(tokens);
                    by_answer[res].push_back(v);
                }
                
                // Choose the answer that keeps the most possibilities (adversarial)
                string chosen_answer;
                int max_size = 0;
                for (auto& p : by_answer) {
                    if ((int)p.second.size() > max_size) {
                        max_size = p.second.size();
                        chosen_answer = p.first;
                    }
                }
                
                // Update possible set
                set<int> new_possible;
                for (int v : by_answer[chosen_answer]) {
                    new_possible.insert(v);
                }
                possible = new_possible;
                
                cout << chosen_answer << endl;
                cout.flush();
                
            } else if (line[0] == '!') {
                // Answer
                istringstream iss(line.substr(1));
                int guess;
                iss >> guess;
                
                if (guess < 1 || guess > n) {
                    quitf(_wa, "Invalid guess: %d", guess);
                }
                
                // Adaptive interactor logic:
                // If there are multiple possible vertices, the interactor can choose
                // any one that is NOT the contestant's guess (if such exists).
                // Only accept if contestant has narrowed down to exactly this guess.
                
                if (possible.size() > 1) {
                    // Multiple possibilities remain - adaptive interactor picks a different one
                    int actual = -1;
                    for (int v : possible) {
                        if (v != guess) {
                            actual = v;
                            break;
                        }
                    }
                    if (actual != -1) {
                        cout << "Wrong" << endl;
                        cout.flush();
                        quitf(_wa, "Wrong answer in round %d: guessed %d but %d possibilities remain (actual was %d)", 
                              round + 1, guess, (int)possible.size(), actual);
                    }
                }
                
                // possible.size() == 1, check if guess matches
                if (possible.count(guess) == 0) {
                    cout << "Wrong" << endl;
                    cout.flush();
                    quitf(_wa, "Wrong answer in round %d: guessed %d but it's not consistent with previous answers", round + 1, guess);
                }
                
                // Correct: contestant narrowed down to exactly one vertex and guessed it
                cout << "Correct" << endl;
                cout.flush();
                
                max_queries = max(max_queries, queries_this_round);
                break;
            } else {
                quitf(_wa, "Invalid command: %s", line.c_str());
            }
        }
    }
    
    // Compute score: P = K + 20 * max_queries
    long long P = (long long)K + 20LL * max_queries;
    
    // Score mapping (from statement):
    // P <= 1700: score = 100 (full)
    // P >= 4500: score = 0
    // Otherwise: score = 100 * (4500 - P) / 2800
    
    // baseline = 4500 (0 score), best = 1700 (full score)
    long long baseline_value = 4500;
    long long best_value = 1700;
    
    double score_ratio = max(0.0, min(1.0, (double)(baseline_value - P) / (double)(baseline_value - best_value)));
    double unbounded_ratio = max(0.0, (double)(baseline_value - P) / (double)(baseline_value - best_value));
    
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", P, score_ratio, unbounded_ratio);
    return 0;
}
