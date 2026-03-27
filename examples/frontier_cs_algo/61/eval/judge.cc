#include "testlib.h"
#include <vector>
#include <algorithm>
using namespace std;

int main(int argc, char * argv[]) {
    registerTestlibCmd(argc, argv);
    
    int T = inf.readInt();
    int total_cases = 0;
    double total_ratio = 0;
    double total_unbounded_ratio = 0;
    
    for (int tc = 1; tc <= T; tc++) {
        int n = inf.readInt();
        int m = inf.readInt();
        long long c = inf.readLong();
        
        vector<long long> a(n + 1, 0);
        for (int i = 1; i <= n; i++) {
            long long ai = inf.readLong();
            a[i] = a[i-1] + ai;
        }
        
        vector<long long> b(m + 1, 0);
        for (int i = 1; i <= m; i++) {
            long long bi = inf.readLong();
            b[i] = b[i-1] + bi;
        }
        
        // Read reference answer
        long long ref_score = ans.readLong();
        
        // Read participant's answer
        int d = ouf.readInt(1, n, format("d for test case %d", tc));
        
        vector<pair<int,int>> segments;
        for (int i = 0; i < d; i++) {
            int l = ouf.readInt(1, n, format("l for segment %d in test case %d", i+1, tc));
            int r = ouf.readInt(l, n, format("r for segment %d in test case %d", i+1, tc));
            segments.push_back({l, r});
        }
        
        // Validate segments
        vector<bool> covered(n + 1, false);
        for (auto [l, r] : segments) {
            for (int day = l; day <= r; day++) {
                if (covered[day]) {
                    quitf(_wa, "Day %d is covered multiple times in test case %d", day, tc);
                }
                covered[day] = true;
            }
        }
        
        for (int day = 1; day <= n; day++) {
            if (!covered[day]) {
                quitf(_wa, "Day %d is not covered in test case %d", day, tc);
            }
        }
        
        // Check chronological order
        for (int i = 0; i + 1 < d; i++) {
            if (segments[i].second >= segments[i+1].first) {
                quitf(_wa, "Segments are not in chronological order in test case %d", tc);
            }
        }
        
        // Calculate participant's score
        long long total_ranks = 0;
        for (auto [l, r] : segments) {
            long long exp = a[r] - a[l-1];
            int rank = 0;
            for (int k = 1; k <= m; k++) {
                if (exp >= b[k]) rank = k;
                else break;
            }
            total_ranks += rank;
        }
        
        long long participant_score = total_ranks - c * d;
        
        if (participant_score < ref_score) {
            quitf(_wa, "Test case %d: score %lld is less than reference %lld", 
                  tc, participant_score, ref_score);
        }
        
        double ratio = min(1.0, (double)participant_score / ref_score * 0.8);
        double unbounded_ratio = (double)participant_score / ref_score * 0.8;
        
        total_ratio += ratio;
        total_unbounded_ratio += unbounded_ratio;
        total_cases++;
    }
    
    total_ratio /= total_cases;
    total_unbounded_ratio /= total_cases;
    double score = total_ratio * 100;
    double unbounded_score = total_unbounded_ratio * 100;
    
    if (!ouf.seekEof()) {
        quitf(_wa, "Extra output found");
    }
    
    string msg = format(
        "Correct! Ratio: %.6f (Score: %.2f). RatioUnbounded: %.6f (ScoreUnbounded: %.2f)",
        total_ratio, score, total_unbounded_ratio, unbounded_score);
    
    quitp(total_ratio, msg.c_str());
}