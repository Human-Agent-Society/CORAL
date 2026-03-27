#include <bits/stdc++.h>
#include "testlib.h"
using namespace std;
using ll = long long;
using pii = pair<int, int>;

const int BOARD_SIZE = 6;
const int RED_CAR_ID = 1;
const int EXIT_ROW = 3;

int N;
unordered_map<ll, int> visited;

typedef enum _Dir {
    horizon = 0,
    vertical,
} Dir;

class Vehicle {
public:
    Dir dir;
    vector<pii> locs;

    void update_dir() {
        if (locs.front().first - locs.back().first == 0)
            this->dir = horizon;
        else
            this->dir = vertical;
    }

    pii get_forward_loc() {
        int cr = locs.front().first;
        int cc = locs.front().second;
        int nr, nc;
        if (dir == vertical) {
            nr = cr - 1;
            nc = cc;
        }
        else {
            nr = cr;
            nc = cc - 1;
        }
        return { nr, nc };
    }

    pii get_backward_loc() {
        int cr = locs.back().first;
        int cc = locs.back().second;
        int nr, nc;
        if (dir == vertical) {
            nr = cr + 1;
            nc = cc;
        }
        else {
            nr = cr;
            nc = cc + 1;
        }
        return { nr, nc };
    }

    bool forward_unmovable(int nr, int nc, ll graph, int step) {
        if (nr < 0 || 6 <= nr || nc < 0 || 6 <= nc || graph & (1LL << (nr * 6 + nc)))
            return true;
        graph |= (1LL << (nr * 6 + nc));
        graph ^= (1LL << (locs.back().first * 6 + locs.back().second));
        if (visited.find(graph) != visited.end() && visited[graph] <= step)
            return true;
        return false;
    }

    bool back_unmovable(int nr, int nc, ll graph, int step) {
        if (nr < 0 || 6 <= nr || nc < 0 || 6 <= nc || graph & (1LL << (nr * 6 + nc)))
            return true;
        graph |= (1LL << (nr * 6 + nc));
        graph ^= (1LL << (locs.front().first * 6 + locs.front().second));
        if (visited.find(graph) != visited.end() && visited[graph] <= step)
            return true;
        return false;
    }

    ll move_foward(ll graph) {
        graph ^= (1LL << (locs.back().first * 6 + locs.back().second));
        if (dir == vertical)
            for (pii& loc : locs)
                loc.first--;
        else
            for (pii& loc : locs)
                loc.second--;
        graph |= (1LL << (locs.front().first * 6 + locs.front().second));
        return graph;
    }

    ll move_backward(ll graph) {
        graph ^= (1LL << (locs.front().first * 6 + locs.front().second));
        if (dir == vertical)
            for (pii& loc : locs)
                loc.first++;
        else
            for (pii& loc : locs)
                loc.second++;
        graph |= (1LL << (locs.back().first * 6 + locs.back().second));
        return graph;
    }
};

Vehicle vehicles[25];
vector<vector<int>> board(BOARD_SIZE + 1, vector<int>(BOARD_SIZE + 1));
map<int, Vehicle> vehicle_map;

void DFS(int step, int& min_step, ll graph) {
    if (vehicles[1].locs.back().second == 5) {
        if (step < min_step) {
            min_step = step;
        }
        return;
    }
    if (step >= min_step - 1) return;

    for (int i = 1; i <= N; i++) {
        Vehicle& curr = vehicles[i];
        auto [nr, nc] = curr.get_forward_loc();
        if (curr.forward_unmovable(nr, nc, graph, step) == false) {
            ll new_graph = curr.move_foward(graph);
            visited[new_graph] = step;
            DFS(step + 1, min_step, new_graph);
            curr.move_backward(graph);
        }
        auto [nnr, nnc] = curr.get_backward_loc();
        if (curr.back_unmovable(nnr, nnc, graph, step) == false) {
            ll new_graph = curr.move_backward(graph);
            visited[new_graph] = step;
            DFS(step + 1, min_step, new_graph);
            curr.move_foward(graph);
        }
    }
}

int solvePuzzle() {
    visited.clear();
    ll start_graph = 0;
    N = 0;
    
    // Clear vehicles
    for (int i = 0; i < 25; i++) {
        vehicles[i].locs.clear();
    }
    
    // Parse board
    for (int i = 0; i < 6; i++) {
        for (int j = 0; j < 6; j++) {
            int val = board[i+1][j+1];
            if (val) {
                vehicles[val].locs.push_back({ i, j });
                start_graph |= (1LL << (i * 6 + j));
                N = max(N, val);
            }
        }
    }
    
    for (int i = 1; i <= N; i++)
        vehicles[i].update_dir();
    
    visited.insert({ start_graph, 0 });
    
    int min_step = 10000;
    DFS(0, min_step, start_graph);
    
    if (min_step < 10000) {
        return min_step + 2;  // +2 to get red car completely out
    }
    return -1;
}

void parseBoard() {
    vehicle_map.clear();
    for (int i = 1; i <= BOARD_SIZE; i++) {
        for (int j = 1; j <= BOARD_SIZE; j++) {
            int id = board[i][j];
            if (id > 0) {
                if (vehicle_map.find(id) == vehicle_map.end()) {
                    vehicle_map[id].dir = horizon;
                }
                vehicle_map[id].locs.push_back({i, j});
            }
        }
    }
    
    for (auto& p : vehicle_map) {
        Vehicle& v = p.second;
        sort(v.locs.begin(), v.locs.end());
        if (v.locs.size() >= 2) {
            if (v.locs[0].first == v.locs[1].first) {
                v.dir = horizon;
            } else {
                v.dir = vertical;
            }
        }
    }
}

bool isValidMove(int vehicle_id, char direction) {
    if (vehicle_map.find(vehicle_id) == vehicle_map.end()) {
        return false;
    }
    
    Vehicle& v = vehicle_map[vehicle_id];
    
    if (v.dir == horizon && (direction != 'L' && direction != 'R')) {
        return false;
    }
    if (v.dir == vertical && (direction != 'U' && direction != 'D')) {
        return false;
    }
    
    vector<pair<int, int>> new_positions = v.locs;
    for (auto& pos : new_positions) {
        if (direction == 'U') pos.first--;
        else if (direction == 'D') pos.first++;
        else if (direction == 'L') pos.second--;
        else if (direction == 'R') pos.second++;
    }
    
    for (auto& pos : new_positions) {
        if (pos.first < 1 || pos.first > BOARD_SIZE || 
            pos.second < 1 || pos.second > BOARD_SIZE) {
            return false;
        }
    }
    
    for (auto& pos : new_positions) {
        int occupant = board[pos.first][pos.second];
        if (occupant != 0 && occupant != vehicle_id) {
            return false;
        }
    }
    
    return true;
}

void applyMove(int vehicle_id, char direction) {
    Vehicle& v = vehicle_map[vehicle_id];
    
    for (auto& pos : v.locs) {
        board[pos.first][pos.second] = 0;
    }
    
    for (auto& pos : v.locs) {
        if (direction == 'U') pos.first--;
        else if (direction == 'D') pos.first++;
        else if (direction == 'L') pos.second--;
        else if (direction == 'R') pos.second++;
    }
    
    for (auto& pos : v.locs) {
        board[pos.first][pos.second] = vehicle_id;
    }
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    for (int i = 1; i <= BOARD_SIZE; i++) {
        for (int j = 1; j <= BOARD_SIZE; j++) {
            board[i][j] = inf.readInt();
        }
    }
    
    parseBoard();
    
    int ref_min_steps = ans.readInt();
    int ref_num_moves = ans.readInt();
    
    if (ouf.seekEof()) {
        quitf(_wa, "No output provided");
    }
    
    int participant_min_steps = ouf.readInt();
    int participant_num_moves = ouf.readInt();
    
    if (participant_min_steps < 0) {
        quitf(_wa, "Minimum steps cannot be negative: %d", participant_min_steps);
    }
    
    if (participant_num_moves < 0) {
        quitf(_wa, "Number of formation moves cannot be negative: %d", participant_num_moves);
    }
    
    vector<pair<int, char>> moves;
    for (int i = 0; i < participant_num_moves; i++) {
        if (ouf.seekEof()) {
            quitf(_wa, "Expected %d formation moves, but only found %d", participant_num_moves, i);
        }
        
        int vehicle_id = ouf.readInt();
        string dir_str = ouf.readToken();
        
        if (dir_str.length() != 1) {
            quitf(_wa, "Invalid direction at move %d: %s", i + 1, dir_str.c_str());
        }
        
        char direction = dir_str[0];
        if (direction != 'U' && direction != 'D' && direction != 'L' && direction != 'R') {
            quitf(_wa, "Invalid direction at move %d: %c", i + 1, direction);
        }
        
        moves.push_back({vehicle_id, direction});
    }
    
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output found after %d formation moves", participant_num_moves);
    }
    
    for (int i = 0; i < participant_num_moves; i++) {
        int vehicle_id = moves[i].first;
        char direction = moves[i].second;
        
        if (!isValidMove(vehicle_id, direction)) {
            quitf(_wa, "Invalid formation move %d: vehicle %d direction %c", 
                  i + 1, vehicle_id, direction);
        }
        
        applyMove(vehicle_id, direction);
    }
    
    parseBoard();
    
    int actual_min_steps = solvePuzzle();
    
    if (actual_min_steps < 0) {
        quitf(_wa, "The formed puzzle is not solvable");
    }
    
    if (actual_min_steps != participant_min_steps) {
        quitf(_wa, "Claimed minimum steps %d does not match actual %d", 
              participant_min_steps, actual_min_steps);
    }
    
    double score_ratio = (double)(participant_min_steps + 1) / (ref_min_steps + 1);
    double unbounded_ratio = score_ratio;
    score_ratio = min(1.0, score_ratio);
    
    quitp(score_ratio, "New puzzle min steps: %d (ref: %d). Ratio: %.6f, RatioUnbounded: %.6f", 
          participant_min_steps, ref_min_steps, score_ratio, unbounded_ratio);
    
    return 0;
}