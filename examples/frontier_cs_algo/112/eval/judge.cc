#include<bits/stdc++.h>
#include "testlib.h"
using namespace std;

const double EPS_SPHERE = 1e-9;      // Very strict for sphere constraint
const double EPS_DISTANCE = 1e-6;    // For distance comparison (as per problem statement)

int n;

double distance(double x1, double y1, double z1, double x2, double y2, double z2) {
    double dx = x1 - x2;
    double dy = y1 - y2;
    double dz = z1 - z2;
    return sqrt(dx * dx + dy * dy + dz * dz);
}

bool doubleEqual(double a, double b, double eps) {
    // Handle both absolute and relative error
    if (abs(a) < eps && abs(b) < eps) return true;
    return abs(a - b) <= eps * max(1.0, max(abs(a), abs(b)));
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    // Read input
    n = inf.readInt();
    
    // Read reference answer
    double ref_answer = ans.readDouble();
    
    // Read participant's output
    if (ouf.seekEof()) {
        quitf(_wa, "No output provided");
    }
    
    double claimed_min_dist = ouf.readDouble();
    
    if (claimed_min_dist < 0) {
        quitf(_wa, "Minimum distance cannot be negative: %.10f", claimed_min_dist);
    }
    
    vector<tuple<double, double, double>> points;
    
    // Read all n points
    for (int i = 0; i < n; i++) {
        if (ouf.seekEof()) {
            quitf(_wa, "Expected %d points, but only found %d", n, i);
        }
        
        double x = ouf.readDouble();
        double y = ouf.readDouble();
        double z = ouf.readDouble();
        
        // Check if point is within unit sphere (strict tolerance)
        double dist_from_origin = sqrt(x * x + y * y + z * z);
        if (dist_from_origin > 1.0 + EPS_SPHERE) {
            quitf(_wa, "Point %d at (%.10f, %.10f, %.10f) is outside the unit sphere (distance from origin: %.15f)", 
                  i + 1, x, y, z, dist_from_origin);
        }
        
        points.push_back({x, y, z});
    }
    
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output found after %d points", n);
    }
    
    // Calculate actual minimum pairwise distance
    double actual_min_dist = 1e18;
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            double d = distance(get<0>(points[i]), get<1>(points[i]), get<2>(points[i]),
                              get<0>(points[j]), get<1>(points[j]), get<2>(points[j]));
            actual_min_dist = min(actual_min_dist, d);
        }
    }
    
    // Verify claimed distance matches actual distance (looser tolerance)
    if (!doubleEqual(actual_min_dist, claimed_min_dist, EPS_DISTANCE)) {
        quitf(_wa, "Claimed minimum distance %.10f does not match actual minimum distance %.10f (difference: %.10f)", 
              claimed_min_dist, actual_min_dist, abs(claimed_min_dist - actual_min_dist));
    }
    
    // Calculate score
    double score_ratio = claimed_min_dist / ref_answer;
    if (score_ratio < 0) score_ratio = 0.0;
    double unbounded_ratio = max(0.0, score_ratio);
    score_ratio = min(1.0, score_ratio);
    
    quitp(score_ratio, "Min distance: %.10f. Ratio: %.6f, RatioUnbounded: %.6f", claimed_min_dist, score_ratio, unbounded_ratio);
    
    return 0;
}