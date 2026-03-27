#include "testlib.h"

#include <bits/stdc++.h>
using namespace std;

static inline string trimStr(const string& s) {
    size_t b = 0;
    while (b < s.size() && isspace((unsigned char)s[b])) b++;
    size_t e = s.size();
    while (e > b && isspace((unsigned char)s[e - 1])) e--;
    return s.substr(b, e - b);
}

static inline vector<string> splitWS(const string& s) {
    vector<string> out;
    string cur;
    for (char ch : s) {
        if (isspace((unsigned char)ch)) {
            if (!cur.empty()) {
                out.push_back(cur);
                cur.clear();
            }
        } else {
            cur.push_back(ch);
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

static inline bool parseLLStrict(const string& s, long long& v) {
    if (s.empty()) return false;
    int i = 0;
    bool neg = false;
    if (s[i] == '-') {
        neg = true;
        i++;
    }
    if (i >= (int)s.size()) return false;
    long long x = 0;
    for (; i < (int)s.size(); i++) {
        char c = s[i];
        if (c < '0' || c > '9') return false;
        int d = c - '0';
        if (x > (LLONG_MAX - d) / 10) return false;
        x = x * 10 + d;
    }
    v = neg ? -x : x;
    return true;
}

struct BlueBase {
    long long fuel;
    long long missiles;
};

struct RedBase {
    long long defense;
    long long value;
    bool destroyed() const { return defense <= 0; }
};

struct Fighter {
    int x, y;
    long long capFuel, capMissiles;
    long long fuel, missiles;
};

static inline long long keyXY(int x, int y) {
    return (long long)x << 32 | (unsigned int)y;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // -------- Input --------
    int n = inf.readInt(1, 200);
    int m = inf.readInt(1, 200);
    vector<string> grid(n);
    for (int i = 0; i < n; i++) {
        grid[i] = inf.readToken();
        if ((int)grid[i].size() != m) quitf(_fail, "invalid input: grid width mismatch");
    }

    unordered_map<long long, BlueBase> blue;
    unordered_map<long long, RedBase> red;

    int nb = inf.readInt(0, 40000);
    for (int i = 0; i < nb; i++) {
        int x = inf.readInt(0, n - 1);
        int y = inf.readInt(0, m - 1);
        long long g = inf.readLong(0LL, 1000LL);
        long long c = inf.readLong(0LL, 2000LL);
        // Blue-side defense/value are unused; allow 0 for compatibility with released datasets.
        long long d = inf.readLong(0LL, 10LL);
        long long v = inf.readLong(0LL, 200LL);
        (void)d;
        (void)v;
        blue[keyXY(x, y)] = BlueBase{g, c};
    }

    int nr = inf.readInt(0, 40000);
    long long best_possible = 0;
    for (int i = 0; i < nr; i++) {
        int x = inf.readInt(0, n - 1);
        int y = inf.readInt(0, m - 1);
        long long g = inf.readLong(0LL, 1000LL);
        long long c = inf.readLong(0LL, 2000LL);
        // Some released datasets may contain 0 defense/value; allow it and treat as non-contributing.
        long long d = inf.readLong(0LL, 10LL);
        long long v = inf.readLong(0LL, 200LL);
        (void)g;
        (void)c;
        red[keyXY(x, y)] = RedBase{d, v};
        best_possible += v;
    }

    int k = inf.readInt(1, 10);
    vector<Fighter> fighters(k);
    for (int i = 0; i < k; i++) {
        int x = inf.readInt(0, n - 1);
        int y = inf.readInt(0, m - 1);
        long long capG = inf.readLong(1LL, 1000LL);
        long long capC = inf.readLong(1LL, 1000LL);
        fighters[i] = Fighter{x, y, capG, capC, 0, 0};
    }

    // Optional ans (not required); keep compatibility with go-judge.
    // Some problems store baseline/best in .ans. Here we compute from input directly.
    (void)ans;

    // -------- Simulation --------
    const int MAX_FRAMES = 15000;
    const int dx[4] = {-1, 1, 0, 0};
    const int dy[4] = {0, 0, -1, 1};

    auto is_red_blocked = [&](int x, int y) -> bool {
        auto it = red.find(keyXY(x, y));
        if (it == red.end()) return false;
        return !it->second.destroyed();
    };

    auto is_blue_base = [&](int x, int y) -> bool {
        return blue.find(keyXY(x, y)) != blue.end();
    };

    long long score_value = 0;

    // Read contestant output frame-by-frame using line-based parsing.
    // Invalid lines/commands are ignored.
    for (int frame = 1; frame <= MAX_FRAMES; frame++) {
        if (ouf.seekEof()) break;

        vector<char> moved_ok(k, 0);

        while (true) {
            if (ouf.seekEof()) {
                // Output ended; remaining frames are no-ops.
                frame = MAX_FRAMES + 1;
                break;
            }
            string line = ouf.readLine();
            line = trimStr(line);
            if (line.empty()) continue;
            if (line == "OK") break;

            vector<string> tok = splitWS(line);
            if (tok.empty()) continue;

            const string& cmd = tok[0];

            auto get_id = [&](int& id_out) -> bool {
                if ((int)tok.size() < 2) return false;
                long long tmp;
                if (!parseLLStrict(tok[1], tmp)) return false;
                if (tmp < 0 || tmp >= k) return false;
                id_out = (int)tmp;
                return true;
            };

            if (cmd == "move") {
                if ((int)tok.size() != 3) continue;
                int id;
                if (!get_id(id)) continue;
                long long dirLL;
                if (!parseLLStrict(tok[2], dirLL)) continue;
                if (dirLL < 0 || dirLL > 3) continue;
                int dir = (int)dirLL;

                if (moved_ok[id]) {
                    // already moved successfully this frame
                    continue;
                }
                Fighter& f = fighters[id];
                if (f.fuel <= 0) {
                    continue;
                }
                int nx = f.x + dx[dir];
                int ny = f.y + dy[dir];
                if (nx < 0 || nx >= n || ny < 0 || ny >= m) {
                    continue;
                }
                if (is_red_blocked(nx, ny)) {
                    continue;
                }
                // successful move: consume fuel and move
                f.fuel -= 1;
                f.x = nx;
                f.y = ny;
                moved_ok[id] = 1;
                continue;
            }

            if (cmd == "fuel") {
                if ((int)tok.size() != 3) continue;
                int id;
                if (!get_id(id)) continue;
                long long cnt;
                if (!parseLLStrict(tok[2], cnt)) continue;
                if (cnt <= 0) continue;
                Fighter& f = fighters[id];
                if (!is_blue_base(f.x, f.y)) continue;
                auto it = blue.find(keyXY(f.x, f.y));
                if (it == blue.end()) continue;
                BlueBase& b = it->second;
                if (b.fuel < cnt) continue;
                if (f.fuel + cnt > f.capFuel) continue;
                b.fuel -= cnt;
                f.fuel += cnt;
                continue;
            }

            if (cmd == "missile") {
                if ((int)tok.size() != 3) continue;
                int id;
                if (!get_id(id)) continue;
                long long cnt;
                if (!parseLLStrict(tok[2], cnt)) continue;
                if (cnt <= 0) continue;
                Fighter& f = fighters[id];
                if (!is_blue_base(f.x, f.y)) continue;
                auto it = blue.find(keyXY(f.x, f.y));
                if (it == blue.end()) continue;
                BlueBase& b = it->second;
                if (b.missiles < cnt) continue;
                if (f.missiles + cnt > f.capMissiles) continue;
                b.missiles -= cnt;
                f.missiles += cnt;
                continue;
            }

            if (cmd == "attack") {
                if ((int)tok.size() != 4) continue;
                int id;
                if (!get_id(id)) continue;
                long long dirLL, cnt;
                if (!parseLLStrict(tok[2], dirLL)) continue;
                if (!parseLLStrict(tok[3], cnt)) continue;
                if (dirLL < 0 || dirLL > 3) continue;
                if (cnt <= 0) continue;
                int dir = (int)dirLL;

                Fighter& f = fighters[id];
                if (f.missiles < cnt) continue;

                int tx = f.x + dx[dir];
                int ty = f.y + dy[dir];
                if (tx < 0 || tx >= n || ty < 0 || ty >= m) continue;

                auto it = red.find(keyXY(tx, ty));
                if (it == red.end()) continue;
                RedBase& rb = it->second;
                if (rb.destroyed()) continue;

                // apply attack
                f.missiles -= cnt;
                rb.defense -= cnt;
                if (rb.destroyed()) {
                    score_value += rb.value;
                }
                continue;
            }

            // Unknown command: ignore.
        }
    }

    // -------- Scoring --------
    // Normalize by the maximum achievable score for this test.
    double ratio = 0.0;
    if (best_possible > 0) {
        ratio = (double)score_value / (double)best_possible;
    }
    ratio = max(0.0, min(1.0, ratio));
    double unbounded_ratio = (best_possible > 0) ? ((double)score_value / (double)best_possible) : 0.0;

    // IMPORTANT: keep "Ratio:" substring for the platform parser.
    quitp(ratio, "Ratio: %.9f, RatioUnbounded: %.9f, Value: %lld, BestPossible: %lld",
          ratio, unbounded_ratio, score_value, best_possible);
}


