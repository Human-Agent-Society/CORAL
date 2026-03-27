#include<bits/stdc++.h>
#include "testlib.h"
using namespace std;

int n;
vector<int> applyMove(const vector<int>& perm, int x, int y) {
    vector<int> result = perm;
    int element = result[x - 1];
    result.erase(result.begin() + x - 1);
    result.insert(result.begin() + y - 1, element);
    return result;
}
bool isSorted(const vector<int>& perm) {
    for (int i = 0; i < (int)perm.size(); i++) {
        if (perm[i] != i + 1) return false;
    }
    return true;
}
bool validateMoves(vector<int> perm, const vector<pair<int, int>>& moves, long long& totalCost) {
    totalCost = 0;
    for (const auto& move : moves) {
        int x = move.first, y = move.second;
        if (x < 1 || x > (int)perm.size() || y < 1 || y > (int)perm.size()) {
            return false;
        }
        perm = applyMove(perm, x, y);
        totalCost += y;
    }
    return isSorted(perm);
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    n = inf.readInt();
    vector<int> original_perm(n);
    for (int i = 0; i < n; i++) {
        original_perm[i] = inf.readInt();
    }
    long long best_answer = ans.readLong();
    long long participant_cost;
    int len_moves;
    vector<pair<int, int>> moves;
    if (ouf.seekEof()) {
        quitf(_wa, "No output provided");
    }
    participant_cost = ouf.readLong();
    len_moves = ouf.readInt();
    if (len_moves < 0) {
        quitf(_wa, "Number of moves cannot be negative: %d", len_moves);
    }
    for (int i = 0; i < len_moves; i++) {
        if (ouf.seekEof()) {
            quitf(_wa, "Expected %d moves, but only found %d", len_moves, i);
        }
        int x = ouf.readInt();
        int y = ouf.readInt();
        if (x < 1 || x > n || y < 1 || y > n) {
            quitf(_wa, "Invalid move %d: x=%d, y=%d (must be between 1 and %d)", i+1, x, y, n);
        }
        moves.push_back({x, y});
    }
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output found after %d moves", len_moves);
    }
    long long actual_cost;
    if (!validateMoves(original_perm, moves, actual_cost)) {
        quitf(_wa, "The given sequence of moves does not sort the permutation");
    }
    if (1LL * (actual_cost + 1) * (len_moves + 1) != participant_cost) {
        quitf(_wa, "Claimed cost %lld does not match actual cost %lld from moves", participant_cost, actual_cost);
    }
    double score_ratio = (double)best_answer / participant_cost;
    double unbounded_score_ratio = max(0.0, score_ratio);
    score_ratio = min(1.0, score_ratio); 
    quitp(score_ratio, "Cost: %lld. Ratio: %.6f, RatioUnbounded: %.6f", participant_cost, score_ratio, unbounded_score_ratio);
    return 0;
}