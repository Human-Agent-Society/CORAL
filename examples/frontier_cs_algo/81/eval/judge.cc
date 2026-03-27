#include "testlib.h"
#include <string>
#include <cassert>


namespace {

    constexpr int N_MAX = 1000, M_MAX = 1002, Q_MAX = 1000;
    int N;
    std::string S;
    int query_count = 0, query_m_max = 0, full_score = 1;
    int a[M_MAX + 10], b[M_MAX + 10];

    int Query() {
        int memory = 0;
        for (int i = 0; i < N; i++) {
            if (S[i] == '0') {
            memory = a[memory];
            }
            if (S[i] == '1') {
            memory = b[memory];
            }
        }
        return memory;
    }
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    N=inf.readInt();
    S=ans.readString();
    assert((int)S.size()==N);
    println(N);
    int op=ouf.readInt();
    while(op){
        query_count++;
        if(query_count>Q_MAX) quitf(_wa, "Too many queries");
        int m=ouf.readInt();
        if(!(1<=m && m<=M_MAX)) quitf(_wa, "Invalid m");
        for(int i=0;i<m;i++) a[i]=ouf.readInt();
        for(int i=0;i<m;i++) b[i]=ouf.readInt();
        for(int i=0;i<m;i++){
            if(!(0<=a[i] && a[i]<m)) quitf(_wa, "Invalid a[%d]", i);
            if(!(0<=b[i] && b[i]<m)) quitf(_wa, "Invalid b[%d]", i);
        }
        if(m>query_m_max) query_m_max=m;

        int res=Query();
        println(res);

        op=ouf.readInt();
    }
    char ch=ouf.readChar();
    std::string s = ouf.readString();
    if ((int)s.size() != N) quitf(_wa, "Invalid guess length");
    for(int i=0;i<N;i++){
        if(!(s[i]=='0' || s[i]=='1')) quitf(_wa, "Invalid character in guess");
        if(s[i]!=S[i]) quitf(_wa, "Wrong guess");
    }
    int value = 100;
    if(query_m_max > 102) value = 10 + (query_m_max - 1002) * (query_m_max - 1002) / 9000;
    double score = 1.0 * full_score * (value / 100);
    quitp(score, "query_m_max=%d, Ratio: %.4f",  query_m_max,score);
    return 0;
}
