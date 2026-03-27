#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <set>
#include <cmath>
#include <algorithm>

using namespace std;

const double K = 0.6;
const double eps = 1e-7;

// Calculate Euclidean distance
double get_dist(double x1, double y1, double x2, double y2) {
    return sqrt((x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2));
}

// Calculate slope (height difference / horizontal difference)
double get_slope(double x1, double y1, double x2, double y2) {
    if (y2 <= y1) return 0.0;  // No cost for descent or level flight
    double dx = fabs(x1 - x2);
    if (dx < eps) return 1e9;  // Avoid division by zero
    return max(0.0 ,(y2 - y1) / dx);
}

// Parse a single pair (id,p) from string
pair<int, int> parsePair(const string& s, int pos, int& nextPos) {
    if (pos >= (int)s.length() || s[pos] != '(') {
        return make_pair(-1, -1);  // Invalid format
    }
    pos++;  // Skip '('
    
    int id = 0;
    while (pos < (int)s.length() && s[pos] >= '0' && s[pos] <= '9') {
        id = id * 10 + (s[pos] - '0');
        pos++;
    }
    
    if (pos >= (int)s.length() || s[pos] != ',') {
        return make_pair(-1, -1);  // Invalid format
    }
    pos++;  // Skip ','
    
    int p = 0;
    while (pos < (int)s.length() && s[pos] >= '0' && s[pos] <= '9') {
        p = p * 10 + (s[pos] - '0');
        pos++;
    }
    
    if (pos >= (int)s.length() || s[pos] != ')') {
        return make_pair(-1, -1);  // Invalid format
    }
    pos++;  // Skip ')'
    
    nextPos = pos;
    return make_pair(id, p);
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input
    double base = inf.readDouble();  // Optimal solution cost
    int M = inf.readInt();  // Number of cities
    
    if (M < 2 || M > 200) {
        quitf(_fail, "Invalid input: M=%d (expected 2 to 200)", M);
    }
    
    vector<int> n(M + 1);  // Number of landing points for each city (1-indexed)
    vector<double> x(M + 1);  // X coordinate for each city (1-indexed)
    vector<vector<double>> y(M + 1);  // Y coordinates for each city's landing points (1-indexed)
    
    for (int i = 1; i <= M; i++) {
        n[i] = inf.readInt();
        x[i] = inf.readDouble();
        
        if (n[i] < 1 || n[i] > 20) {
            quitf(_fail, "Invalid input: n[%d]=%d (expected 1 to 20)", i, n[i]);
        }
        
        y[i].resize(n[i] + 1);  // 1-indexed
        for (int j = 1; j <= n[i]; j++) {
            y[i][j] = inf.readDouble();
        }
    }
    
    double D_original = inf.readDouble();  // Normalization constant for distance
    double S_original = inf.readDouble();  // Normalization constant for slope
    
    // Preprocess D and S according to original checker logic
    // This matches the original checker's preprocessing
    double D = (1.0 - K) / D_original;
    double S = K / S_original;
    
    // Read user output: format is (id1,p1)@(id2,p2)@...@(idM,pM)
    // Use readToken to read the entire line, then parse manually
    string userOutput = ouf.readLine();
    
    vector<pair<int, int>> path;  // Path: (city_id, point_index) pairs
    set<int> visitedCities;  // Track visited cities to check for duplicates
    
    // Parse the output string manually
    int pos = 0;
    int pairCount = 0;
    
    while (pos < (int)userOutput.length()) {
        // Skip whitespace
        while (pos < (int)userOutput.length() && (userOutput[pos] == ' ' || userOutput[pos] == '\t' || userOutput[pos] == '\n')) {
            pos++;
        }
        
        if (pos >= (int)userOutput.length()) break;
        
        // Expect '('
        if (userOutput[pos] != '(') {
            quitf(_wa, "Invalid output format: expected '(' at position %d, found '%c'", pos, userOutput[pos]);
        }
        pos++;
        
        // Read city ID (integer)
        int cityId = 0;
        bool hasDigits = false;
        while (pos < (int)userOutput.length() && userOutput[pos] >= '0' && userOutput[pos] <= '9') {
            cityId = cityId * 10 + (userOutput[pos] - '0');
            pos++;
            hasDigits = true;
        }
        
        if (!hasDigits || cityId == 0) {
            quitf(_wa, "Invalid output format: expected city ID (positive integer) after '(' at position %d", pos);
        }
        
        // Expect ','
        if (pos >= (int)userOutput.length() || userOutput[pos] != ',') {
            quitf(_wa, "Invalid output format: expected ',' after city ID at position %d", pos);
        }
        pos++;
        
        // Read landing point index (integer)
        int pointIdx = 0;
        hasDigits = false;
        while (pos < (int)userOutput.length() && userOutput[pos] >= '0' && userOutput[pos] <= '9') {
            pointIdx = pointIdx * 10 + (userOutput[pos] - '0');
            pos++;
            hasDigits = true;
        }
        
        if (!hasDigits || pointIdx == 0) {
            quitf(_wa, "Invalid output format: expected landing point index (positive integer) after ',' at position %d", pos);
        }
        
        // Expect ')'
        if (pos >= (int)userOutput.length() || userOutput[pos] != ')') {
            quitf(_wa, "Invalid output format: expected ')' after landing point index at position %d", pos);
        }
        pos++;
        
        // Validate city ID
        if (cityId < 1 || cityId > M) {
            quitf(_wa, "Invalid city ID: %d (expected 1 to %d)", cityId, M);
        }
        
        // Validate point index
        if (pointIdx < 1 || pointIdx > n[cityId]) {
            quitf(_wa, "Invalid landing point index: %d for city %d (expected 1 to %d)", pointIdx, cityId, n[cityId]);
        }
        
        // Check for duplicate cities
        if (visitedCities.count(cityId)) {
            quitf(_wa, "City %d is visited more than once", cityId);
        }
        visitedCities.insert(cityId);
        
        path.push_back(make_pair(cityId, pointIdx));
        pairCount++;
        
        // Skip whitespace
        while (pos < (int)userOutput.length() && (userOutput[pos] == ' ' || userOutput[pos] == '\t' || userOutput[pos] == '\n')) {
            pos++;
        }
        
        // Check if there's a '@' separator (except for the last pair)
        if (pairCount < M) {
            if (pos >= (int)userOutput.length() || userOutput[pos] != '@') {
                quitf(_wa, "Expected '@' separator after pair %d, found character at position %d", pairCount, pos);
            }
            pos++;  // Skip '@'
        }
    }
    
    // Check if exactly M pairs were provided
    if (pairCount != M) {
        quitf(_wa, "Expected %d city pairs, found %d", M, pairCount);
    }
    
    // Check if all cities were visited
    if ((int)visitedCities.size() != M) {
        quitf(_wa, "Not all cities were visited: visited %d out of %d", (int)visitedCities.size(), M);
    }
    
    // Calculate cost of the user's path
    double total_dist = 0.0;
    double total_slope = 0.0;
    
    for (int i = 0; i < M; i++) {
        int cityId1 = path[i].first;
        int pointIdx1 = path[i].second;
        int cityId2 = path[(i + 1) % M].first;  // Next city (wrap around to first)
        int pointIdx2 = path[(i + 1) % M].second;
        
        double x1 = x[cityId1];
        double y1 = y[cityId1][pointIdx1];
        double x2 = x[cityId2];
        double y2 = y[cityId2][pointIdx2];
        
        total_dist += get_dist(x1, y1, x2, y2);
        total_slope += get_slope(x1, y1, x2, y2);
    }
    
    // Calculate cost using the formula from original checker:
    double userCost = total_dist * D + total_slope * S;
    
    // Calculate score based on base (optimal solution)
    // Score formula: if userCost <= base, score = 1.0
    //                if userCost > base * (1 + base/1500000), score = 0.0
    //                otherwise, linear interpolation: (upper - userCost) / (upper - base)
    double upperBound = base * (1.0 + base / 100000.0);
    double score_ratio;
    
    if (userCost <= base) {
        score_ratio = 1.0;  // Perfect or better than optimal
    } else if (userCost > upperBound) {
        score_ratio = 0.0;  // Exceeds upper bound
    } else {
        // Linear decrease from 1.0 to 0.0 as cost increases from base to upperBound
        score_ratio = (upperBound - userCost) / (upperBound - base);
    }
    
    // Ensure score is in [0.0, 1.0]
    score_ratio = max(0.0, min(1.0, score_ratio));
    double unbounded_ratio = score_ratio;
    
    // Use standard quitp format
    quitp(score_ratio, "Value: %.4f. Ratio: %.4f, RatioUnbounded: %.4f", userCost, score_ratio, unbounded_ratio);
    
    return 0;
}
