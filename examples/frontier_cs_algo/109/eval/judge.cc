// chk.cc
#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

static inline bool isKnight(int r1,int c1,int r2,int c2){
    int dr=abs(r1-r2), dc=abs(c1-c2);
    return (dr==1 && dc==2) || (dr==2 && dc==1);
}
static inline long long idxOf(int r,int c,int N){ return 1LL*(r-1)*N + (c-1); }

static bool readMaybeLong(InStream& S, long long &x){
    try { x = S.readLong(); return true; }
    catch(...) { return false; }
}
static bool readMaybeInt(InStream& S, int &x){
    try { x = S.readInt(); return true; }
    catch(...) { return false; }
}

static void validatePath(const vector<pair<int,int>>& path, int N, const char* who){
    vector<char> seen(1LL*N*N, 0);
    for (size_t i=0;i<path.size();++i){
        int r=path[i].first, c=path[i].second;
        if (r<1||r>N||c<1||c>N){
            if (string(who)=="participant") quitp(0.0, "Cell (%d,%d) out of bounds. Score=0.0", r,c);
            quitf(_fail, "Answer file: cell (%d,%d) out of bounds.", r,c);
        }
        long long id = idxOf(r,c,N);
        if (seen[id]){
            if (string(who)=="participant") quitp(0.0, "Square (%d,%d) revisited at step %zu. Score=0.0", r,c,i+1);
            quitf(_fail, "Answer file: square (%d,%d) revisited at step %zu.", r,c,i+1);
        }
        seen[id]=1;
        if (i>0){
            int pr=path[i-1].first, pc=path[i-1].second;
            if (!isKnight(pr,pc,r,c)){
                if (string(who)=="participant")
                    quitp(0.0, "Illegal move from (%d,%d) to (%d,%d) at step %zu. Score=0.0",pr,pc,r,c,i+1);
                quitf(_fail, "Answer file: illegal move from (%d,%d) to (%d,%d) at step %zu.",pr,pc,r,c,i+1);
            }
        }
    }
}

/*
Length-first ONLY format:

L
r1 c1
r2 c2
...
rL cL

- Must have (r1,c1) == (r0,c0).
- Reads exactly L pairs.
- On participant side, L == 0 is allowed (empty path -> score 0).
- On answer side, L must be >= 1.
- Any extra tokens after the L pairs are ignored (no readEof requirement).
*/
static vector<pair<int,int>> readPathLenOnly(InStream& S, int N, int r0, int c0,
                                             const char* who, bool allowZeroLen)
{
    vector<pair<int,int>> path;

    long long L;
    if (!readMaybeLong(S, L)) {
        if (string(who)=="participant") quitp(0.0, "Empty output (no length). Score=0.0");
        quitf(_fail, "Answer file is empty (no length).");
    }

    if (L < 0 || L > 1LL*N*N) {
        if (string(who)=="participant") quitp(0.0, "Invalid length header %lld. Score=0.0", L);
        quitf(_fail, "Answer file: invalid length header %lld.", L);
    }

    if (L == 0) {
        if (!allowZeroLen) quitf(_fail, "Answer file: zero length not allowed.");
        // Participant explicit zero-length: OK; ignore any trailing tokens.
        return path;
    }

    // Read exactly L pairs
    int r, c;
    // First pair must be the start
    if (!readMaybeInt(S, r) || !readMaybeInt(S, c)) {
        if (string(who)=="participant") quitp(0.0, "Output ended before first pair. Score=0.0");
        quitf(_fail, "Answer file: ended before first pair.");
    }
    if (r != r0 || c != c0) {
        if (string(who)=="participant")
            quitp(0.0, "Path does not start at (%d,%d). Got (%d,%d). Score=0.0", r0,c0,r,c);
        quitf(_fail, "Answer file: path does not start at (%d,%d). Got (%d,%d).", r0,c0,r,c);
    }
    path.emplace_back(r,c);

    for (long long i = 1; i < L; ++i) {
        if (!readMaybeInt(S, r) || !readMaybeInt(S, c)) {
            if (string(who)=="participant") quitp(0.0, "Output ended before %lld pairs declared. Score=0.0", L);
            quitf(_fail, "Answer file: ended before %lld pairs declared.", L);
        }
        path.emplace_back(r,c);
    }

    validatePath(path, N, who);
    return path;
}

int main(int argc, char* argv[]){
    registerTestlibCmd(argc, argv);

    if (argc < 4) {
        quitf(_fail, "Usage: %s in.txt out.txt ans.txt", argv[0]);
    }

    // Optional quick existence/emptiness check for ans.txt
    {
        ifstream f(argv[3], ios::binary);
        if (!f) quitf(_fail, "Cannot open %s", argv[3]);
        f.seekg(0, ios::end);
        if (f.tellg() == 0) quitf(_fail, "ans.txt is empty (0 bytes) inside sandbox.");
    }

    // Input (in.txt): N r0 c0
    int N,r0,c0;
    try { N=inf.readInt(); r0=inf.readInt(); c0=inf.readInt(); }
    catch(...) { quitf(_fail,"Failed to read N, r0, c0 from input"); }
    if (N<1) quitf(_fail,"Invalid N=%d",N);
    if (r0<1||r0>N||c0<1||c0>N) quitf(_fail,"Start (r0=%d,c0=%d) out of bounds",r0,c0);

    // Read answer & participant (length-first only).
    // Answer: L >= 1. Participant: L >= 0 (allows zero-length).
    auto bestPath = readPathLenOnly(ans, N, r0, c0, "answer", /*allowZeroLen=*/false);
    long long Best = (long long)bestPath.size();

    auto yourPath = readPathLenOnly(ouf, N, r0, c0, "participant", /*allowZeroLen=*/true);
    int Your = (int)yourPath.size();

    double ratio = (Best==0)?0.0: (double)Your/(double)Best;
    if (ratio<0) ratio=0;
    double unbounded_ratio = max(0.0, ratio);
    if (ratio>1) ratio=1;

    // Keep exact token (with space) your engine parses:
    quitp(ratio, "Valid knight path. Your=%d Best=%lld Ratio: %.8f, RatioUnbounded: %.8f", Your, Best, ratio, unbounded_ratio);
}
