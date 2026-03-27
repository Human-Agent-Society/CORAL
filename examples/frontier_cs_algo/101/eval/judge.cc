#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <string>
#include "testlib.h"
using namespace std;

enum {
    INVALID_INPUT = -1,
    INVALID_T_LENGTH = 1,
    INVALID_T_CHAR   = 2,
    WRONG_T          = 3,
    INVALID_S_LENGTH = 4,
    INVALID_S_CHAR   = 5,
    QUERY_LIMIT_EXCEEDED = 6,
    INVALID_OUTPUT   = 9,
};

const int N_MAX = 8000;
const int QUERY_LIMIT = 5000;

int N, R;
std::vector<int> U, V;
std::string T;
int QUERY_COUNT = 0;

double score(int x){
    if (x <= 900) return 1.0;
    if (x >= 5000) return 0.0;
    return (5000.0 - x) / (5000.0 - 900.0);
}

double score_unbounded(int x){
    if (x >= 5000) return 0.0;
    return (5000.0 - x) / (5000.0 - 900.0);
}

[[noreturn]] void wrong(const int num) {
    fprintf(stdout, "-1\n");
    fflush(stdout);
    quitf(_wa, "translate:wrong\nWrong Answer [%d]\n", num);
}

[[noreturn]] void ok() {
    double r  = score(QUERY_COUNT);
    double ru = score_unbounded(QUERY_COUNT);
    quitp(r, "Ratio: %.4f , RatioUnbounded: %.4f , Queries: %d", r, ru, QUERY_COUNT);
}

int query(std::string s) {
    const int M = 2 * N + 1;
    if ((int)s.size() != M) {
        wrong(INVALID_S_LENGTH);
    }
    for (char c : s) {
        if (c != '0' && c != '1') wrong(INVALID_S_CHAR);
    }
    if (QUERY_COUNT == QUERY_LIMIT) {
        wrong(QUERY_LIMIT_EXCEEDED);
    }
    QUERY_COUNT++;

    for (char &c : s) c -= '0';

    for (int i = N - 1; i >= 0; --i) {
        const int u = U[i], v = V[i];
        if (T[i] == '&') {
            s[i] ^= (s[u] & s[v]);
        } else {
            s[i] ^= (s[u] | s[v]);
        }
    }
    return s[0];
}

void answer(std::string t) {
    if ((int)t.size() != N) {
        wrong(INVALID_T_LENGTH);
    }
    for (char c : t) {
        if (c != '&' && c != '|') wrong(INVALID_T_CHAR);
    }
    if (t != T) {
        wrong(WRONG_T);
    }
    ok();
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    N = inf.readInt();
    R = inf.readInt();
    if (N < 1 || N > N_MAX) {
        wrong(INVALID_INPUT);
    }
    cout << N << " " << R << endl;

    U.resize(N);
    V.resize(N);
    for (int i = 0; i < N; ++i) {
        U[i] = inf.readInt();
        V[i] = inf.readInt();
        cout << U[i] << " " << V[i] << endl;
    }

    T = inf.readToken();
    if ((int)T.size() != N) {
        wrong(INVALID_INPUT);
    }
    int orCount = 0;
    for (char c : T) {
        if (c != '&' && c != '|') wrong(INVALID_INPUT);
        if (c == '|') ++orCount;
    }
    if (orCount > R) {
        wrong(INVALID_INPUT);
    }

    while (true) {
        std::string op = ouf.readToken();
        if (op.empty()) wrong(INVALID_OUTPUT);
        const char type = op[0];
        if (type != '?' && type != '!') wrong(INVALID_OUTPUT);

        std::string payload = ouf.readToken();

        if (!payload.empty() && payload.back() == '\n') payload.pop_back();

        if (type == '?') {
            int res = query(payload);
            fprintf(stdout, "%d\n", res);
            fflush(stdout);
        } else {
            answer(payload);
        }
    }
}
