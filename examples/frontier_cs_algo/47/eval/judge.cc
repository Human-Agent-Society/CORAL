#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct Item { long long w,h,v,limit; };
struct BinSpec { long long W,H; bool allow_rotate; };

void skipWS(InStream& s){ while(!s.eof() && isspace(s.curChar())) s.readChar(); }
void expectChar(InStream& s, char c){ skipWS(s); char got = s.readChar(); if (got!=c) quitf(_fail,"Expected '%c' but got '%c'", c, got); }
string readString(InStream& s){
    skipWS(s);
    expectChar(s, '"');
    string out; char c;
    while(true){
        c = s.readChar();
        if (c=='"') break;
        if (c=='\\'){
            char e = s.readChar();
            switch(e){
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                default: out.push_back(e); break;
            }
        } else {
            out.push_back(c);
        }
    }
    return out;
}
long long readJsonLong(InStream& s){
    skipWS(s);
    bool neg=false;
    if (s.curChar()=='+' || s.curChar()=='-'){ neg = (s.curChar()=='-'); s.readChar(); }
    if (!isdigit(s.curChar())) quitf(_fail, "Expected integer digit, got '%c'", s.curChar());
    long long val = 0;
    while(!s.eof() && isdigit(s.curChar())){
        int d = s.curChar()-'0';
        if (val > (LLONG_MAX - d)/10) quitf(_fail, "Integer overflow");
        val = val*10 + d;
        s.readChar();
    }
    return neg ? -val : val;
}
bool readJsonBool(InStream& s){
    skipWS(s);
    if (s.curChar()=='t'){ string ex="true"; for(char c:ex){ if (s.readChar()!=c) quitf(_fail,"Malformed boolean"); } return true; }
    if (s.curChar()=='f'){ string ex="false"; for(char c:ex){ if (s.readChar()!=c) quitf(_fail,"Malformed boolean"); } return false; }
    quitf(_fail, "Expected boolean"); return false;
}

void parseInput(map<string,Item>& items, BinSpec& bin){
    expectChar(inf,'{');
    for (int iter=0; iter<2; ++iter){
        if (iter>0){ expectChar(inf, ','); }
        string k = readString(inf);
        expectChar(inf, ':');
        if (k=="bin"){
            expectChar(inf, '{');
            bool first=true; long long mask=0;
            for (int i=0;i<3;i++){
                if (!first) expectChar(inf, ','); first=false;
                string bk = readString(inf);
                expectChar(inf, ':');
                if (bk=="W"){ bin.W = readJsonLong(inf); mask|=1; }
                else if (bk=="H"){ bin.H = readJsonLong(inf); mask|=2; }
                else if (bk=="allow_rotate"){ bin.allow_rotate = readJsonBool(inf); mask|=4; }
                else quitf(_fail, "Unknown bin key: %s", bk.c_str());
            }
            if (mask!=7) quitf(_fail, "Missing bin fields");
            expectChar(inf, '}');
        }else if (k=="items"){
            expectChar(inf, '[');
            bool first = true;
            while(true){
                skipWS(inf);
                if (inf.curChar()==']'){ inf.readChar(); break; }
                if (!first) expectChar(inf, ',');
                first=false;
                expectChar(inf, '{');
                string t; long long w=0,h=0,v=0,limit=0; long long mask=0;
                bool firstIt=true;
                for (int fld=0; fld<5; ++fld){
                    if (!firstIt){ expectChar(inf, ','); } firstIt=false;
                    string key = readString(inf);
                    expectChar(inf, ':');
                    if (key=="type"){ t = readString(inf); mask|=1; }
                    else if (key=="w"){ w = readJsonLong(inf); mask|=2; }
                    else if (key=="h"){ h = readJsonLong(inf); mask|=4; }
                    else if (key=="v"){ v = readJsonLong(inf); mask|=8; }
                    else if (key=="limit"){ limit = readJsonLong(inf); mask|=16; }
                    else quitf(_fail, "Unknown item field: %s", key.c_str());
                }
                expectChar(inf, '}');
                if (mask!=31) quitf(_fail, "Missing fields in item");
                if (w<=0||h<=0||v<0||limit<0) quitf(_wa, "Invalid item parameters for %s", t.c_str());
                items[t] = Item{w,h,v,limit};
            }
        }else quitf(_fail, "Unknown top-level key: %s", k.c_str());
    }
    expectChar(inf, '}');
    if (items.empty()) quitf(_fail, "No items in input");
}

struct Place { string t; long long x,y; int rot; long long w,h; };
vector<Place> parseOutput(const map<string,Item>& items, const BinSpec& bin){
    vector<Place> res;
    expectChar(ouf, '{');
    string k = readString(ouf);
    expectChar(ouf, ':');
    if (k!="placements") quitf(_wa, "Top-level key must be \"placements\"");
    expectChar(ouf, '[');
    bool first = true;
    while(true){
        skipWS(ouf);
        if (ouf.curChar()==']'){ ouf.readChar(); break; }
        if (!first) expectChar(ouf, ',');
        first=false;
        expectChar(ouf, '{');
        string t; long long x=0,y=0; int rot=0; long long mask = 0;
        bool firstF = true;
        while(true){
            skipWS(ouf);
            if (!firstF){
                if (ouf.curChar()=='}') break;
                expectChar(ouf, ',');
            }
            firstF=false;
            string kk = readString(ouf);
            expectChar(ouf, ':');
            if (kk=="type"){ t = readString(ouf); mask|=1; }
            else if (kk=="x"){ x = readJsonLong(ouf); mask|=2; }
            else if (kk=="y"){ y = readJsonLong(ouf); mask|=4; }
            else if (kk=="rot"){ long long b = readJsonLong(ouf); rot = (int)(b!=0); mask|=8; }
            else quitf(_wa,"Unknown field in placement: %s", kk.c_str());
        }
        expectChar(ouf, '}');
        if (mask!=15) quitf(_wa,"Missing one of required fields in a placement");
        auto it = items.find(t);
        if (it==items.end()) quitf(_wa,"Unknown item type in placement: %s", t.c_str());
        if (rot && !bin.allow_rotate) quitf(_wa,"Rotation not allowed by this test");
        long long w = rot ? it->second.h : it->second.w;
        long long h = rot ? it->second.w : it->second.h;
        if (x < 0 || y < 0 || x + w > bin.W || y + h > bin.H) quitf(_wa,"Placement of %s is out of bin bounds", t.c_str());
        res.push_back(Place{t,x,y,rot,w,h});
    }
    expectChar(ouf, '}');
    return res;
}

long long evaluate(const vector<Place>& P, const map<string,Item>& items){
    unordered_map<string,long long> used;
    used.reserve(P.size()*2+1);
    for (auto &p: P){
        used[p.t]++;
        const auto &it = items.at(p.t);
        if (used[p.t] > it.limit) quitf(_wa, "Used too many items of type %s", p.t.c_str());
    }
    struct Ev { long long x; int id; bool open; };
    vector<Ev> ev; ev.reserve(P.size()*2);
    for (int i=0;i<(int)P.size();++i){
        ev.push_back({P[i].x, i, true});
        ev.push_back({P[i].x + P[i].w, i, false});
    }
    // IMPORTANT: process close events BEFORE open events at the same x
    sort(ev.begin(), ev.end(), [](const Ev&a, const Ev&b){
        if (a.x != b.x) return a.x < b.x;
        return a.open < b.open; // close (false) first
    });
    struct Seg { long long y1,y2; int id; };
    struct Cmp { bool operator()(Seg const& a, Seg const& b) const {
        if (a.y1!=b.y1) return a.y1<b.y1;
        if (a.y2!=b.y2) return a.y2<b.y2;
        return a.id<b.id;
    }};
    std::set<Seg, Cmp> active;
    for (auto &e: ev){
        const auto &r = P[e.id];
        if (e.open){
            Seg s{r.y, r.y + r.h, e.id};
            auto it = active.lower_bound(s);
            if (it!=active.end()){
                if (!(it->y1 >= s.y2 || it->y2 <= s.y1)) quitf(_wa, "Rectangles overlap");
            }
            if (it!=active.begin()){
                auto it2 = prev(it);
                if (!(it2->y1 >= s.y2 || it2->y2 <= s.y1)) quitf(_wa, "Rectangles overlap");
            }
            active.insert(s);
        }else{
            Seg s{r.y, r.y + r.h, e.id};
            auto it = active.find(s);
            if (it!=active.end()) active.erase(it);
        }
    }
    long long value=0;
    for (auto &p: P) value += items.at(p.t).v;
    return value;
}

int main(int argc, char* argv[]){
    registerTestlibCmd(argc, argv);
    map<string,Item> items;
    BinSpec bin;
    parseInput(items, bin);
    vector<Place> P = parseOutput(items, bin);
    long long baseline = ans.readLong();
    long long best = ans.readLong();
    long long value = evaluate(P, items);
    double ratio, unbounded_ratio = 0.0;
    if (best <= baseline){
        ratio = (value >= best) ? 1.0 : 0.0;
    }else{
        ratio = (double)(value - baseline) / (double)(best - baseline);
        if (ratio < 0) ratio = 0;
        unbounded_ratio = std::max(0.0, ratio);
        if (ratio > 1) ratio = 1;
    }
    quitp(ratio, "Value: %lld. Ratio: %.6f, RatioUnbounded: %.6f", value, ratio, unbounded_ratio);
}
