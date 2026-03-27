// checker.cpp
// C++11 testlib special judge for the Slitherlink-like problem.
// Fully reproduces behavior of the original Python+Z3 checker.
// Requires testlib.h in include path.

#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

const int N = 12;
const vector<string> M = {
    "?   ?   ??? ",
    "?? ??  ?   ?",
    "? ? ?  ?   ?",
    "? ? ?  ???? ",
    "? ? ?  ?    ",
    "?   ?  ?    ",
    "            ",
    "?  ?   ?????",
    "? ?      ?  ",
    "??   ? ? ?  ",
    "? ?  ? ? ?  ",
    "?  ? ??? ?  "
};

string valid_char;
vector<string> grid;

// helper printing to stderr (like original)
void eprint(const string &s){ cerr << s << "\n"; }
void myAssert(bool cond, const string &msg){
    if(!cond) {
        // In SPJ we usually call quitf for WA, but here follow original: print to stderr and exit
        quitf(_pe, "Assertion failed: %s", msg.c_str());
    }
}

string clean_line(string line){
    const string allowed = " 0123";
    while(!line.empty() && allowed.find(line.front())==string::npos) line.erase(line.begin());
    while(!line.empty() && allowed.find(line.back())==string::npos) line.pop_back();
    return line;
}

vector<string> readSol(InStream &in){
    vector<string> res;
    for(int i=0;i<N;i++){
        string line = in.readLine();
        line = clean_line(line);
        myAssert((int)line.size()==12, "The size of the result should be 12 * 12");
        for(int j=0;j<12;j++){
            char c = line[j];
            myAssert(valid_char.find(c)!=string::npos, string("Invalid char ") + c);
            if(c != ' ')
                myAssert(M[i][j] == '?', "Position (" + to_string(i) + "," + to_string(j) + ") should be empty");
            else
                myAssert(M[i][j] == ' ', "Position (" + to_string(i) + "," + to_string(j) + ") should be non-empty");
        }
        res.push_back(line);
    }
    return res;
}

// Edge representation
struct Edge {
    bool is_h; // horizontal if true, vertical if false
    int i, j;  // coordinates: H[i][j] or V[i][j]
    vector<pair<int,int>> adj_cells;  // adjacent cells (r,c)
    vector<pair<int,int>> adj_points; // endpoints (pi,pj)
    int score; // heuristic: number of adjacent numbered cells
};

vector<Edge> edges;
int Ecnt;

// Backtracking state
vector<int> edge_val; // -1 unassigned, 0 false, 1 true
int cell_assigned_true[N][N];
int cell_unassigned[N][N];
int point_deg[N+1][N+1];
int point_unassigned[N+1][N+1];

struct Change {
    int type; // 0: edge val, 1: cell_assigned_true, 2: cell_unassigned, 3: point_deg, 4: point_unassigned
    int a;    // encoded index (edge idx or r*100 + c or pi*100 + pj)
    int old;
};
vector<Change> changes;

void apply_assign(int eidx, int val){
    // assume edge_val[eidx] == -1
    changes.push_back({0, eidx, edge_val[eidx]});
    edge_val[eidx] = val;
    const Edge &ed = edges[eidx];
    // adjacent cells
    for(size_t k=0;k<ed.adj_cells.size();++k){
        int r = ed.adj_cells[k].first;
        int c = ed.adj_cells[k].second;
        changes.push_back({2, r*100 + c, cell_unassigned[r][c]});
        cell_unassigned[r][c]--;
        if(val == 1){
            changes.push_back({1, r*100 + c, cell_assigned_true[r][c]});
            cell_assigned_true[r][c]++;
        }
    }
    // endpoints
    for(size_t k=0;k<ed.adj_points.size();++k){
        int pi = ed.adj_points[k].first;
        int pj = ed.adj_points[k].second;
        changes.push_back({4, pi*100 + pj, point_unassigned[pi][pj]});
        point_unassigned[pi][pj]--;
        if(val == 1){
            changes.push_back({3, pi*100 + pj, point_deg[pi][pj]});
            point_deg[pi][pj]++;
        }
    }
}

void rollback_to(int sz){
    while((int)changes.size() > sz){
        Change ch = changes.back(); changes.pop_back();
        if(ch.type == 0){
            edge_val[ch.a] = ch.old;
        } else if(ch.type == 1){
            int r = ch.a / 100, c = ch.a % 100;
            cell_assigned_true[r][c] = ch.old;
        } else if(ch.type == 2){
            int r = ch.a / 100, c = ch.a % 100;
            cell_unassigned[r][c] = ch.old;
        } else if(ch.type == 3){
            int pi = ch.a / 100, pj = ch.a % 100;
            point_deg[pi][pj] = ch.old;
        } else if(ch.type == 4){
            int pi = ch.a / 100, pj = ch.a % 100;
            point_unassigned[pi][pj] = ch.old;
        }
    }
}

// Propagation: enforce cell counts and point degree constraints (0 or 2)
bool contradiction_check_and_propagate(){
    bool changed = true;
    int iter = 0;
    while(changed){
        changed = false;
        iter++;
        if(iter > 300000) break; // safety
        // cells
        for(int r=0;r<N;r++){
            for(int c=0;c<N;c++){
                char ch = grid[r][c];
                if(ch == ' ') continue;
                int need = ch - '0';
                int have = cell_assigned_true[r][c];
                int rem = cell_unassigned[r][c];
                if(have > need) return false;
                if(have + rem < need) return false;
                if(rem == 0){
                    if(have != need) return false;
                } else {
                    if(have == need){
                        // force remaining adjacent edges false
                        for(int e=0;e<Ecnt;e++){
                            if(edge_val[e] != -1) continue;
                            for(size_t k=0;k<edges[e].adj_cells.size();++k){
                                if(edges[e].adj_cells[k].first==r && edges[e].adj_cells[k].second==c){
                                    apply_assign(e, 0);
                                    changed = true;
                                    break;
                                }
                            }
                        }
                    } else if(have + rem == need){
                        // force remaining adjacent edges true
                        for(int e=0;e<Ecnt;e++){
                            if(edge_val[e] != -1) continue;
                            for(size_t k=0;k<edges[e].adj_cells.size();++k){
                                if(edges[e].adj_cells[k].first==r && edges[e].adj_cells[k].second==c){
                                    apply_assign(e, 1);
                                    changed = true;
                                    break;
                                }
                            }
                        }
                    }
                }
            }
        }
        // points: degree must be 0 or 2
        for(int pi=0; pi<=N; ++pi){
            for(int pj=0; pj<=N; ++pj){
                int deg = point_deg[pi][pj];
                int rem = point_unassigned[pi][pj];
                bool possible0 = (deg <= 0 && 0 <= deg + rem);
                bool possible2 = (deg <= 2 && 2 <= deg + rem);
                if(!possible0 && !possible2) return false;
                if(rem == 0){
                    if(!(deg == 0 || deg == 2)) return false;
                } else {
                    if(possible0 && !possible2){
                        // only 0 possible -> all remaining edges adjacent must be false
                        for(int e=0;e<Ecnt;e++){
                            if(edge_val[e] != -1) continue;
                            for(size_t k=0;k<edges[e].adj_points.size();++k){
                                if(edges[e].adj_points[k].first==pi && edges[e].adj_points[k].second==pj){
                                    apply_assign(e, 0);
                                    changed = true;
                                    break;
                                }
                            }
                        }
                    } else if(!possible0 && possible2){
                        int need_true = 2 - deg;
                        if(need_true < 0) return false;
                        if(need_true == 0){
                            for(int e=0;e<Ecnt;e++){
                                if(edge_val[e] != -1) continue;
                                for(size_t k=0;k<edges[e].adj_points.size();++k){
                                    if(edges[e].adj_points[k].first==pi && edges[e].adj_points[k].second==pj){
                                        apply_assign(e, 0);
                                        changed = true;
                                        break;
                                    }
                                }
                            }
                        } else if(need_true == rem){
                            for(int e=0;e<Ecnt;e++){
                                if(edge_val[e] != -1) continue;
                                for(size_t k=0;k<edges[e].adj_points.size();++k){
                                    if(edges[e].adj_points[k].first==pi && edges[e].adj_points[k].second==pj){
                                        apply_assign(e, 1);
                                        changed = true;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return true;
}

// branching heuristic: prefer edges adjacent to numbered cells
int pick_next_edge(){
    int best = -1;
    int best_score = -1;
    for(int e=0;e<Ecnt;e++){
        if(edge_val[e] != -1) continue;
        if(edges[e].score > best_score){
            best_score = edges[e].score;
            best = e;
        }
    }
    if(best != -1) return best;
    for(int e=0;e<Ecnt;e++) if(edge_val[e] == -1) return e;
    return -1;
}

// build H/V matrices from edge_val
void build_hv_from_edges(vector<vector<int>> &H, vector<vector<int>> &V){
    H.assign(N+1, vector<int>(N,0));
    V.assign(N, vector<int>(N+1,0));
    for(int e=0;e<Ecnt;e++){
        if(edge_val[e] == 1){
            if(edges[e].is_h) H[edges[e].i][edges[e].j] = 1;
            else V[edges[e].i][edges[e].j] = 1;
        }
    }
}

// split assignment into loops (each loop is vector of (tag,i,j))
vector<vector< tuple<char,int,int> > > split_loops_from_assignment(){
    vector<vector<int> > H(N+1, vector<int>(N,0));
    vector<vector<int> > V(N, vector<int>(N+1,0));
    for(int e=0;e<Ecnt;e++){
        if(edge_val[e] == 1){
            if(edges[e].is_h) H[edges[e].i][edges[e].j] = 1;
            else V[edges[e].i][edges[e].j] = 1;
        }
    }

    auto incident_edges_at_point = [&](int pi, int pj){
        vector< tuple<char,int,int> > res;
        if(pi>0 && V[pi-1][pj]) res.push_back(make_tuple('v', pi-1, pj));
        if(pi < N && V[pi][pj]) res.push_back(make_tuple('v', pi, pj));
        if(pj>0 && H[pi][pj-1]) res.push_back(make_tuple('h', pi, pj-1));
        if(pj < N && H[pi][pj]) res.push_back(make_tuple('h', pi, pj));
        return res;
    };

    auto remove_edge_mat = [&](char tag, int i, int j){
        if(tag=='h') H[i][j] = 0;
        else V[i][j] = 0;
    };

    vector<vector< tuple<char,int,int> > > loop_list;

    while(true){
        bool found_edge = false;
        char start_tag = 0;
        int start_i=-1, start_j=-1;
        for(int i=0;i<=N && !found_edge;i++){
            for(int j=0;j<N && !found_edge;j++){
                if(H[i][j]){ start_tag='h'; start_i=i; start_j=j; found_edge=true; break; }
            }
        }
        for(int i=0;i<N && !found_edge;i++){
            for(int j=0;j<=N && !found_edge;j++){
                if(V[i][j]){ start_tag='v'; start_i=i; start_j=j; found_edge=true; break; }
            }
        }
        if(!found_edge) break;

        int cur_pi = start_i, cur_pj = start_j;
        vector< tuple<char,int,int> > loop;
        char prev_tag = 0; int prev_i = -1, prev_j = -1;
        int init_pi = cur_pi, init_pj = cur_pj;
        while(true){
            vector< tuple<char,int,int> > inc = incident_edges_at_point(cur_pi, cur_pj);
            bool moved = false;
            for(size_t k=0;k<inc.size();++k){
                char t = get<0>(inc[k]);
                int ei = get<1>(inc[k]);
                int ej = get<2>(inc[k]);
                if(prev_tag != 0 && t==prev_tag && ei==prev_i && ej==prev_j) continue;
                loop.push_back(inc[k]);
                remove_edge_mat(t, ei, ej);
                // move to other endpoint
                if(t=='h'){
                    if(cur_pi==ei && cur_pj==ej){
                        prev_tag = 'h'; prev_i = ei; prev_j = ej;
                        cur_pi = ei; cur_pj = ej+1;
                    } else {
                        prev_tag = 'h'; prev_i = ei; prev_j = ej;
                        cur_pi = ei; cur_pj = ej;
                    }
                } else {
                    if(cur_pi==ei && cur_pj==ej){
                        prev_tag = 'v'; prev_i = ei; prev_j = ej;
                        cur_pi = ei+1; cur_pj = ej;
                    } else {
                        prev_tag = 'v'; prev_i = ei; prev_j = ej;
                        cur_pi = ei; cur_pj = ej;
                    }
                }
                moved = true;
                break;
            }
            if(!moved) break;
            if(cur_pi==init_pi && cur_pj==init_pj && !loop.empty()) break;
        }
        if(!loop.empty()) loop_list.push_back(loop);
        else break;
    }
    return loop_list;
}

// generate hv/vv from one loop and check against grid
bool generateSol_from_loop(const vector< tuple<char,int,int> > &loop, vector<vector<int>> &Hout, vector<vector<int>> &Vout){
    Hout.assign(N+1, vector<int>(N,0));
    Vout.assign(N, vector<int>(N+1,0));
    vector<vector<int>> cnt(N, vector<int>(N,0));
    for(size_t k=0;k<loop.size();++k){
        char tag = get<0>(loop[k]);
        int i = get<1>(loop[k]);
        int j = get<2>(loop[k]);
        if(tag=='h'){
            Hout[i][j] = 1;
            if(i < N) cnt[i][j] += 1;
            if(i > 0) cnt[i-1][j] += 1;
        } else {
            Vout[i][j] = 1;
            if(j < N) cnt[i][j] += 1;
            if(j > 0) cnt[i][j-1] += 1;
        }
    }
    for(int i=0;i<N;i++){
        for(int j=0;j<N;j++){
            if(grid[i][j] != ' '){
                int need = grid[i][j] - '0';
                if(cnt[i][j] != need) return false;
            }
        }
    }
    return true;
}

// serialize a solution (H,V) to string for deduplication
string serialize_solution(const vector<vector<int>> &H, const vector<vector<int>> &V){
    string s;
    s.reserve((N+1)*N + N*(N+1) + 10);
    for(int i=0;i<=N;i++){
        for(int j=0;j<N;j++) s.push_back(H[i][j] ? '1' : '0');
        s.push_back('|');
    }
    s.push_back('#');
    for(int i=0;i<N;i++){
        for(int j=0;j<=N;j++) s.push_back(V[i][j] ? '1' : '0');
        s.push_back('|');
    }
    return s;
}

void print_solution_to_stderr(const vector<vector<int>> &H, const vector<vector<int>> &V){
    eprint("Sol:");
    for(int i=0;i<=N;i++){
        string s = " ";
        for(int k=0;k<N;k++){
            s.push_back(H[i][k] ? '-' : ' ');
            if(k+1<N) s.push_back(' ');
        }
        eprint(s);
        if(i!=N){
            string s2;
            for(int p=0;p<=N;p++){
                s2.push_back(V[i][p] ? '|' : ' ');
                if(p!=N) s2.push_back(grid[i][p]);
            }
            eprint(s2);
        }
    }
}

// container for unique solutions
vector<pair<vector<vector<int>>, vector<vector<int>>>> sol_list;
unordered_set<string> sol_set; // serialized strings for dedup

// recursive search (stop when found >= limit_solutions)
bool try_search(int limit_solutions){
    int unassigned = 0;
    for(int e=0;e<Ecnt;e++) if(edge_val[e] == -1) unassigned++;
    if(unassigned == 0){
        // full assignment: split into loops and check each loop individually
        vector<vector< tuple<char,int,int> > > loops = split_loops_from_assignment();
        for(size_t i=0;i<loops.size();++i){
            vector<vector<int>> Hsol, Vsol;
            if(generateSol_from_loop(loops[i], Hsol, Vsol)){
                string key = serialize_solution(Hsol, Vsol);
                if(sol_set.find(key) == sol_set.end()){
                    sol_set.insert(key);
                    sol_list.push_back(make_pair(Hsol, Vsol));
                    if((int)sol_list.size() >= limit_solutions) return true;
                }
            }
        }
        return false;
    }
    int e = pick_next_edge();
    if(e == -1) return false;
    for(int val = 0; val <= 1; ++val){
        int save_sz = (int)changes.size();
        apply_assign(e, val);
        bool ok = contradiction_check_and_propagate();
        if(ok){
            if(try_search(limit_solutions)) return true;
        }
        rollback_to(save_sz);
    }
    return false;
}

int main(int argc, char **argv){
    registerTestlibCmd(argc, argv);

    // read type from input file (inf)
    int w = inf.readInt();
    if(w == 0) valid_char = " 0123";
    else valid_char = " 123";

    // read contestant output (ouf) as grid grid
    grid = readSol(ouf);

    // build edge list
    edges.clear();
    // horizontals H[0..12][0..11]
    for(int i=0;i<=N;i++){
        for(int j=0;j<N;j++){
            Edge ed;
            ed.is_h = true; ed.i = i; ed.j = j; ed.score = 0;
            if(i>0) ed.adj_cells.push_back(make_pair(i-1,j));
            if(i<N) ed.adj_cells.push_back(make_pair(i,j));
            ed.adj_points.push_back(make_pair(i,j));
            ed.adj_points.push_back(make_pair(i,j+1));
            for(size_t k=0;k<ed.adj_cells.size();++k){
                int r = ed.adj_cells[k].first, c = ed.adj_cells[k].second;
                if(grid[r][c] != ' ') ed.score++;
            }
            edges.push_back(ed);
        }
    }
    // verticals V[0..11][0..12]
    for(int i=0;i<N;i++){
        for(int j=0;j<=N;j++){
            Edge ed;
            ed.is_h = false; ed.i = i; ed.j = j; ed.score = 0;
            if(j>0) ed.adj_cells.push_back(make_pair(i,j-1));
            if(j<N) ed.adj_cells.push_back(make_pair(i,j));
            ed.adj_points.push_back(make_pair(i,j));
            ed.adj_points.push_back(make_pair(i+1,j));
            for(size_t k=0;k<ed.adj_cells.size();++k){
                int r = ed.adj_cells[k].first, c = ed.adj_cells[k].second;
                if(grid[r][c] != ' ') ed.score++;
            }
            edges.push_back(ed);
        }
    }
    Ecnt = (int)edges.size();

    // initialize state
    edge_val.assign(Ecnt, -1);
    for(int i=0;i<N;i++) for(int j=0;j<N;j++){
        cell_assigned_true[i][j] = 0;
        cell_unassigned[i][j] = 4;
    }
    for(int i=0;i<=N;i++) for(int j=0;j<=N;j++){
        point_deg[i][j] = 0;
        int t = 0;
        if(i!=0) t++;
        if(i!=N) t++;
        if(j!=0) t++;
        if(j!=N) t++;
        point_unassigned[i][j] = t;
    }

    // run initial propagation
    if(!contradiction_check_and_propagate()){
        // no valid assignment at all
        quitp(0.0, "There is no valid solution");
    }

    // enumerate solutions, stop when 5 found (>=5 -> 0 points)
    sol_list.clear();
    sol_set.clear();
    const int LIMIT = 5;
    try_search(LIMIT);

    int cnt = (int)sol_list.size();

    if(cnt == 0){
        quitp(0.0, "There is no valid solution");
    } else if(cnt == 1){
        // unique -> 100%
        // print solution to stderr
        print_solution_to_stderr(sol_list[0].first, sol_list[0].second);
        quitp(1.0, "Ratio: 1.0 Correct! unique solution");
    } else if(cnt == 2){
        for(int k=0;k<2;k++) print_solution_to_stderr(sol_list[k].first, sol_list[k].second);
        quitp(0.80, "Ratio: 0.8 Two valid solutions");
    } else if(cnt == 3){
        for(int k=0;k<3;k++) print_solution_to_stderr(sol_list[k].first, sol_list[k].second);
        quitp(0.60, "Ratio: 0.6 Three valid solutions");
    } else if(cnt == 4){
        for(int k=0;k<4;k++) print_solution_to_stderr(sol_list[k].first, sol_list[k].second);
        quitp(0.40, "Ratio: 0.4 Four valid solutions");
    } else if(cnt == 5){
        for(int k=0;k<5;k++) print_solution_to_stderr(sol_list[k].first, sol_list[k].second);
        quitp(0.20, "Ratio: 0.2 Five valid solutions");
    } else {
        // >=5
        for(int k=0;k< (int)min((size_t)6, sol_list.size()); ++k) print_solution_to_stderr(sol_list[k].first, sol_list[k].second);
        quitp(0.0, "Ratio: 0.0 Six or more valid solutions (or too many)");
    }
    return 0;
}

