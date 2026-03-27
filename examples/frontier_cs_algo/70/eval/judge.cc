#include "testlib.h"
#include <vector>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <random>

using namespace std;

struct Node {
    int id;
    int degree;
    bool visited;
};

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    int t = inf.readInt();
    cout << t << endl;

    double tot_score = 0.0;
    long long tot_moves = 0.0;
    long long tot_base_move_count = 0.0;
    double tot_unbounded_score = 0.0;

    for (int k = 0; k < t; ++k) {
        int n = inf.readInt(2, 300, "n");
        int m = inf.readInt(1, min(n * (n - 1) / 2, 25 * n), "m");
        int start = inf.readInt(1, n, "start");
        int base_move_count = inf.readInt();

        cout << n << " " << m << " " << start << " " << base_move_count << endl;

        vector<vector<int>> adj(n + 1);
        vector<int> degrees(n + 1, 0);

        for (int i = 0; i < m; ++i) {
            int u = inf.readInt(1, n, "u");
            int v = inf.readInt(1, n, "v");
            adj[u].push_back(v);
            adj[v].push_back(u);
            
            cout << u << " " << v << endl;
        }
        
        for(int i = 1; i <= n; ++i) {
            degrees[i] = adj[i].size();
        }

        std::mt19937 gen(rnd.next(1, 1000000000));
        int curr = start;
        vector<bool> visited(n + 1, false);
        visited[curr] = true;
        int visited_count = 1;
        int moves = 0;
        
        long long limit = 2LL * base_move_count; 
        bool success = false;

        while (moves <= limit) {
            if (visited_count == n) {
                success = true;
                break;
            }
            
            if (moves == limit) {
                break; 
            }

            vector<int> neighbors = adj[curr];
            
            std::shuffle(neighbors.begin(), neighbors.end(), gen);

            int d = neighbors.size();
            cout << d;
            for (int neighbor_idx : neighbors) {
                cout << " " << degrees[neighbor_idx] << " " << (visited[neighbor_idx] ? 1 : 0);
            }
            cout << endl;

            int choice = ouf.readInt(1, d, "choice index");

            curr = neighbors[choice - 1];
            moves++;

            if (!visited[curr]) {
                visited[curr] = true;
                visited_count++;
            }
        }

        tot_moves += moves;
        tot_base_move_count += base_move_count;

        if (success) {
            cout << "AC" << endl;
            
            double current_score = 0.0;
            double moves_dbl = (double)moves;
            double base_dbl = (double)base_move_count;
        
            if (moves <= base_move_count) {
                current_score = 1.0; 
            } else if (moves <= 2 * base_move_count) {
                double numerator = (2.0 * base_dbl) - moves_dbl;
                double ratio = numerator / base_dbl;
                current_score = ratio * ratio;
            } else
                current_score = 0.0;

            double unbounded_score = ((2.0 * base_dbl) - moves_dbl) / base_dbl;
            unbounded_score = unbounded_score * unbounded_score;
            tot_unbounded_score += unbounded_score;
        
            if (current_score < 0)
                current_score = 0.0;
            if (current_score > 1.0)
                current_score = 1.0;
        
            tot_score += current_score;
        } else {
            cout << "F" << endl;
        }
    }

    double score_ratio = tot_score / t;
    double unbounded_score_ratio = tot_unbounded_score / t;
    quitp(score_ratio, "Queries: %lld. Ratio: %.4f, RatioUnbounded: %.4f", tot_moves, score_ratio, unbounded_score_ratio);

    return 0;
}
