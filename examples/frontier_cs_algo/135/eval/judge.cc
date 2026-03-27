#include "testlib.h"
#include <bits/stdc++.h>
#include <csignal>
#include <unistd.h>
#include <cerrno>
using namespace std;

static inline long long stepDist(int a, int b, const vector<int>& pos, int n) {
    int da = pos[a], db = pos[b];
    int diff = abs(da - db);
    return min<long long>(diff, n - diff);
}

// Safe line writer that won't crash on SIGPIPE.
// If the contestant closed its stdin, write() returns -1 with EPIPE.
// We convert that into a friendly quitp(...) message.
static void safe_write_line(const std::string& s) {
    std::string line = s;
    line.push_back('\n');
    ssize_t w = ::write(STDOUT_FILENO, line.data(), line.size());
    if (w < 0) {
        if (errno == EPIPE) {
            quitp(0.0, "Broken pipe to contestant (SIGPIPE). Ratio: 0.0000");
        }
        quitf(_fail, "Interactor write() failed, errno=%d.", errno);
    }
}

int main(int argc, char* argv[]) {
    // Make failed writes return -1/EPIPE instead of terminating the process.
    std::signal(SIGPIPE, SIG_IGN);

    registerInteraction(argc, argv);

    // Read public k, n and send to contestant as one line: "k n"
    const long long kMax = inf.readLong();   // e.g., 12000
    const int n = inf.readInt();
    {
        ostringstream oss;
        oss << kMax << " " << n;
        safe_write_line(oss.str());
    }

    // Read hidden circular order from .ans (clockwise).
    vector<int> order(n);
    for (int i = 0; i < n; ++i) {
        order[i] = ans.readInt();
    }

    // Validate hidden permutation.
    {
        vector<int> seen(n, 0);
        for (int v : order) {
            if (v < 0 || v >= n) {
                quitf(_fail, "Secret answer contains value %d out of range [0, %d].", v, n - 1);
            }
            if (seen[v]) {
                quitf(_fail, "Secret answer is not a permutation: duplicate value %d.", v);
            }
            seen[v] = 1;
        }
    }

    // Position map: label -> clockwise position.
    vector<int> pos(n, -1);
    for (int i = 0; i < n; ++i) pos[order[i]] = i;

    long long query_count = 0;

    try {
        while (true) {
            // Expect either "?" or "!".
            string token = ouf.readToken();

            if (token == "?") {
                int x = ouf.readInt();
                int y = ouf.readInt();
                int z = ouf.readInt();

                if (x < 0 || x >= n || y < 0 || y >= n || z < 0 || z >= n) {
                    quitf(_wa, "Query has value out of range: got (%d, %d, %d) with n=%d.", x, y, z, n);
                }
                if (x == y || y == z || x == z) {
                    quitf(_wa, "Query doors must be distinct: got (%d, %d, %d).", x, y, z);
                }

                if (++query_count > kMax) {
                    // Match the sample interactor's style: include "Ratio: 0.0000"
                    quitp(0.0, "Query limit exceeded. Max queries: %lld. Ratio: 0.0000", kMax);
                }

                long long d_xy = stepDist(x, y, pos, n);
                long long d_yz = stepDist(y, z, pos, n);
                long long d_zx = stepDist(z, x, pos, n);
                long long best = min(d_xy, min(d_yz, d_zx));

                vector<pair<int,int>> winners;
                auto addPair = [&](int a, int b, long long d) {
                    if (d == best) {
                        if (a > b) swap(a, b);
                        winners.emplace_back(a, b);
                    }
                };
                addPair(x, y, d_xy);
                addPair(y, z, d_yz);
                addPair(z, x, d_zx);

                sort(winners.begin(), winners.end());
                winners.erase(unique(winners.begin(), winners.end()), winners.end());

                safe_write_line(to_string((int)winners.size()));
                for (auto &p : winners) {
                    safe_write_line(to_string(p.first) + " " + to_string(p.second));
                }
            }
            else if (token == "!") {
                vector<int> guess(n);
                vector<int> seen(n, 0);
                bool valid_perm = true;
                for (int i = 0; i < n; ++i) {
                    int v = ouf.readInt();
                    if (v < 0 || v >= n || seen[v]) valid_perm = false;
                    else seen[v] = 1;
                    guess[i] = v;
                }

                if (!valid_perm) {
                    quitf(_wa, "Invalid final guess: the sequence is not a valid permutation.");
                }

                int s = pos[guess[0]];
                int s_next = (s + 1) % n;
                int s_prev = (s + n - 1) % n;

                int dir;
                if (pos[guess[1]] == s_next) dir = +1;
                else if (pos[guess[1]] == s_prev) dir = -1;
                else {
                    quitp(0.0, "Wrong guess. Ratio: 0.0000");
                }

                bool ok = true;
                for (int i = 0, p = s; i < n; ++i, p = (p + (dir == +1 ? 1 : (n - 1))) % n) {
                    if (order[p] != guess[i]) { ok = false; break; }
                }

                if (!ok) {
                    quitp(0.0, "Wrong guess. Ratio: 0.0000");
                }

                // Scoring (problem’s formula), message matches the sample’s wording/format:
                double ratio = (double)(kMax - query_count) / 7800.0;
                double unbounded_ratio = max(0.0, ratio);
                ratio = max(0.0, min(1.0, ratio));

                quitp(ratio, "Correct guess in %lld queries. Ratio: %.4f, RatioUnbounded: %.4f", query_count, ratio, unbounded_ratio);
                break; // unreachable
            }
            else {
                quitf(_wa, "Expected '?' or '!' but got token '%s'.", token.c_str());
            }
        }
    } catch (const std::exception& e) {
        // Contestant likely crashed / closed its stdout; convert to a friendly message.
        quitp(0.0, "Interactor read failed (EOF). Contestant likely crashed or closed pipe. Ratio: 0.0000");
    } catch (...) {
        quitp(0.0, "Interactor encountered an unknown read error. Ratio: 0.0000");
    }

    return 0;
}
