#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

// ---------- helpers ----------
static inline bool parse_ll(const string& s, long long& x) {
    if (s.empty()) return false;
    size_t i = 0;
    if (s[0] == '+' || s[0] == '-') i = 1;
    if (i == s.size()) return false;
    for (; i < s.size(); ++i) if (s[i] < '0' || s[i] > '9') return false;
    try {
        size_t pos = 0; long long v = stoll(s, &pos, 10);
        if (pos != s.size()) return false; x = v; return true;
    } catch (...) { return false; }
}
static inline bool parse_int32(const string& s, int& x) {
    long long t; if (!parse_ll(s, t)) return false;
    if (t < INT_MIN || t > INT_MAX) return false; x = (int)t; return true;
}
static inline int mapXO(char ch) { return ch=='X' ? 0 : (ch=='O' ? 1 : -1); }

// Suffix Automaton for distinct substrings count on alphabet {X,O}
struct SAM {
    struct Node { int next[2], link, len; Node(){ next[0]=next[1]=-1; link=-1; len=0; } };
    vector<Node> st; int last;
    explicit SAM(int maxLen=0){ st.reserve(maxLen?2*maxLen:1); st.push_back(Node()); last=0; }
    long long extend(int c){
        if (c<0 || c>1) return 0;
        int cur = (int)st.size(); st.push_back(Node()); st[cur].len = st[last].len+1;
        int p = last;
        for (; p!=-1 && st[p].next[c]==-1; p=st[p].link) st[p].next[c]=cur;
        if (p==-1) st[cur].link=0;
        else{
            int q=st[p].next[c];
            if (st[p].len+1==st[q].len) st[cur].link=q;
            else{
                int clone=(int)st.size(); st.push_back(st[q]); st[clone].len=st[p].len+1;
                for (; p!=-1 && st[p].next[c]==q; p=st[p].link) st[p].next[c]=clone;
                st[q].link=st[cur].link=clone;
            }
        }
        last=cur;
        return (long long)st[cur].len - (long long)st[st[cur].link].len;
    }
};
static long long powerConcat(const string& a, const string& b){
    SAM sam((int)a.size()+(int)b.size());
    long long cnt=0;
    for(char ch: a) cnt += sam.extend(mapXO(ch));
    for(char ch: b) cnt += sam.extend(mapXO(ch));
    return cnt;
}

int main(int argc, char* argv[]) {
    setName("Magic Words interactor (stdout version, exact-pair check)");
    registerInteraction(argc, argv);

    // Public input
    int n = inf.readInt(1, 1000, "n");
    int q = inf.readInt(1, 1000, "q");

    // For scoring
    long long cap = 30LL * n * n;
    long long optimal_total_len = ans.readLong(0, cap, "optimal_total_len");

    // Announce to participant and FLUSH.
    cout << n << ' ' << q << '\n' << flush;

    // Accumulators and error collectors
    vector<string> words(n);
    unordered_set<string> uniq; uniq.reserve(n*2);
    long long total_len = 0;

    vector<string> pe_errors; // format issues
    vector<string> wa_errors; // semantic issues

    auto add_pe = [&](const string& s){ if (pe_errors.size() < 8)  pe_errors.push_back(s); };
    auto add_wa = [&](const string& s){ if (wa_errors.size() < 12) wa_errors.push_back(s); };

    // ---- Read n words as tokens (no early exit) ----
    bool words_chars_ok = true;
    for (int i = 0; i < n; ++i) {
        string s = ouf.readToken();
        words[i] = s;
        total_len += (int)s.size();

        if ((int)s.size() < 1 || (int)s.size() > 30 * n)
            add_wa(format("Invalid length of word %d: %d not in [1,%d]", i+1, (int)s.size(), 30*n));

        bool okChars = true;
        for (int k = 0; k < (int)s.size(); ++k) {
            if (s[k] != 'X' && s[k] != 'O') {
                okChars = false;
                add_wa(format("Invalid character in word %d at pos %d: '%s'", i+1, k+1, compress(string(1,s[k])).c_str()));
                break;
            }
        }
        if (!okChars) words_chars_ok = false;

        if (!uniq.insert(s).second)
            add_wa(format("Duplicate word at index %d", i+1));
    }

    if (total_len > cap) {
        add_wa(format("Total length %s exceeds cap %s", toString(total_len).c_str(), toString(cap).c_str()));
    }

    // ---- Interaction phase: q rounds: print p, then read u v ----
    auto pickPair = [&](int j)->pair<int,int>{
        int u = (j % n) + 1;
        int v = ((j * 37 + 13) % n) + 1;
        return {u, v};
    };

    for (int j = 0; j < q; ++j) {
        // Compute the p for our secret pair this round
        auto [uu, vv] = pickPair(j);
        long long pval = words_chars_ok ? powerConcat(words[uu-1], words[vv-1]) : 0;

        // Send p and FLUSH
        cout << pval << '\n' << flush;

        // Read u, v from participant; collect errors but continue
        string su = ouf.readToken();
        string sv = ouf.readToken();

        int u = 0, v = 0;
        bool pu = parse_int32(su, u);
        bool pv = parse_int32(sv, v);
        if (!pu) add_pe(format("Query %d: expected integer u, got '%s'", j+1, compress(su).c_str()));
        if (!pv) add_pe(format("Query %d: expected integer v, got '%s'", j+1, compress(sv).c_str()));

        if (pu && (u < 1 || u > n))
            add_wa(format("Query %d: u=%d out of range [1,%d]", j+1, u, n));
        if (pv && (v < 1 || v > n))
            add_wa(format("Query %d: v=%d out of range [1,%d]", j+1, v, n));

        if (pu && pv && 1 <= u && u <= n && 1 <= v && v <= n) {
            if (u != uu || v != vv) {
                // Optional: compute what their pair's power is (for a clearer message)
                if (words_chars_ok) {
                    long long got = powerConcat(words[u-1], words[v-1]);
                    if (got == pval) {
                        add_wa(format("Query %d: wrong indices; expected (%d,%d), got (%d,%d) (same power).",
                                      j+1, uu, vv, u, v));
                    } else {
                        add_wa(format("Query %d: wrong indices and wrong power; expected (%d,%d) with p=%s, but (%d,%d) gives %s.",
                                      j+1, uu, vv, toString(pval).c_str(), u, v, toString(got).c_str()));
                    }
                } else {
                    add_wa(format("Query %d: wrong indices; expected (%d,%d), got (%d,%d).",
                                  j+1, uu, vv, u, v));
                }
            }
        }
    }

    // ---- Final verdict ----
    if (!pe_errors.empty()) {
        string msg = "wrong output format";
        for (string &e : pe_errors) msg += "\n - " + e;
        quitf(_pe, "%s", msg.c_str());
    }

    if (!wa_errors.empty()) {
        string msg = "wrong answer";
        for (string &e : wa_errors) msg += "\n - " + e;
        quitp(0.0, "%s", msg.c_str());
    }

    // All good: score by compression ratio
    double denom = double(cap - optimal_total_len);
    double your  = double(cap - total_len);
    double ratio, unbounded_ratio = 0.0;
    if (denom <= 0.0) ratio = (your <= 0.0) ? 1.0 : 0.0;
    else {
        ratio = your / denom;
        if (ratio < 0.0) ratio = 0.0;
        unbounded_ratio = ratio;
        if (ratio > 1.0) ratio = 1.0;
    }

    quitp(ratio,
          "All %d answers valid. Total length = %s, optimal = %s. Ratio: %.4f, RatioUnbounded: %.4f",
          q, toString(total_len).c_str(), toString(optimal_total_len).c_str(), ratio, unbounded_ratio);
}
