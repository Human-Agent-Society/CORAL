#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static const long long COORD_LIMIT = 100000000LL; // 1e8
static const int MAX_D_PER_WAVE = 2000;
static const int TOTAL_PROBE_LIMIT = 20000;

int main(int argc, char* argv[]) {
    // Initialize interactor
    registerInteraction(argc, argv);

    // Read public input from .in: b, k, w
    long long b = inf.readLong();
    int k = inf.readInt();
    int w = inf.readInt();

    // Read secret deposits from .ans: x1 y1 x2 y2 ... xk yk
    vector<pair<long long,long long>> hidden(k);
    for (int i = 0; i < k; ++i) {
        long long x = ans.readLong();
        long long y = ans.readLong();
        // Validate secrets are within [-b, b]
        if (x < -b || x > b || y < -b || y > b) {
            quitf(_fail, "Secret deposit (%lld, %lld) is out of bounds [-%lld, %lld].",
                  x, y, b, b);
        }
        hidden[i] = {x, y};
    }

    // Send public b, k, w to contestant
    cout << b << ' ' << k << ' ' << w << '\n';
    cout.flush();

    auto manhattan = [&](const pair<long long,long long>& a,
                         const pair<long long,long long>& p) -> long long {
        return llabs(a.first - p.first) + llabs(a.second - p.second);
    };

    int wave_count = 0;
    int total_probes = 0;

    while (true) {
        // Expect either "?" for query wave or "!" for final answer

        // --- FIX: read a generic token, not pattern "command"
        string cmd = ouf.readToken();   // accepts "?" or "!"
        // Alternatively:
        // ouf.skipBlanks();
        // char ch = ouf.readChar();
        // string cmd(1, ch);

        if (cmd == "?") {
            // Enforce wave limit
            if (wave_count >= w) {
                quitp(0.0, "Wave limit exceeded. Max waves: %d. Ratio: 0.0000", w);
            }
            ++wave_count;

            // Read d, then d pairs (s_j, t_j)
            int d = ouf.readInt();
            if (d < 1 || d > MAX_D_PER_WAVE) {
                quitp(0.0, "Invalid d=%d in query: must be in [1, %d]. Ratio: 0.0000",
                      d, MAX_D_PER_WAVE);
            }
            if (total_probes + d > TOTAL_PROBE_LIMIT) {
                quitp(0.0, "Probe limit exceeded. Max probes: %d. Ratio: 0.0000",
                      TOTAL_PROBE_LIMIT);
            }

            vector<pair<long long,long long>> probes;
            probes.reserve(d);
            for (int j = 0; j < d; ++j) {
                long long sj = ouf.readLong();
                long long tj = ouf.readLong();
                if (sj < -COORD_LIMIT || sj > COORD_LIMIT ||
                    tj < -COORD_LIMIT || tj > COORD_LIMIT) {
                    quitp(0.0,
                          "Invalid probe coordinate (%lld, %lld): out of range [-%lld, %lld]. Ratio: 0.0000",
                          sj, tj, COORD_LIMIT, COORD_LIMIT);
                }
                probes.push_back({sj, tj});
            }
            total_probes += d;

            // Compute and return sorted distances (k * d numbers)
            vector<long long> distances;
            distances.reserve((size_t)k * (size_t)d);
            for (int i = 0; i < k; ++i) {
                for (int j = 0; j < d; ++j) {
                    distances.push_back(manhattan(hidden[i], probes[j]));
                }
            }
            sort(distances.begin(), distances.end());

            // Output distances in one line
            for (size_t i = 0; i < distances.size(); ++i) {
                if (i) cout << ' ';
                cout << distances[i];
            }
            cout << '\n';
            cout.flush();

        } else if (cmd == "!") {
            // Read exactly k guessed deposit coordinates
            vector<pair<long long,long long>> guess(k);
            for (int i = 0; i < k; ++i) {
                long long x = ouf.readLong();
                long long y = ouf.readLong();
                guess[i] = {x, y};
            }

            // Count matches (order does not matter; match each hidden at most once)
            int found = 0;
            vector<bool> used(k, false);
            for (int i = 0; i < k; ++i) {
                for (int j = 0; j < k; ++j) {
                    if (!used[j] && guess[i].first == hidden[j].first &&
                        guess[i].second == hidden[j].second) {
                        used[j] = true;
                        ++found;
                        break;
                    }
                }
            }

            double ratio = k == 0 ? 1.0 : (double)found / (double)k;
            double unbounded_ratio = max(0.0, ratio);
            ratio = max(0.0, min(1.0, ratio)); // clamp

            if (found == k) {
                quitp(1.0, "All mineral deposits found. Ratio: 1.0000, RatioUnbounded: 1.0000");
            } else {
                quitp(ratio, "Found %d of %d mineral deposits. Ratio: %.4f, RatioUnbounded: %.4f",
                      found, k, ratio, unbounded_ratio);
            }
            break;

        } else {
            quitf(_wa, "Invalid command: expected '?' or '!' but got '%s'", cmd.c_str());
        }
    }

    return 0;
}
