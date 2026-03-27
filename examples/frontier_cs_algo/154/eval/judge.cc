#include <bits/stdc++.h>
using namespace std;
#include "testlib.h"

static const int D = 30;
static const int T = 300;

static const array<pair<size_t,size_t>,4> DIR = {
    make_pair((size_t)-1, (size_t)0),
    make_pair((size_t) 1, (size_t)0),
    make_pair((size_t)0, (size_t)-1),
    make_pair((size_t)0, (size_t) 1)
};
static const array<char,5> DIR_CHAR = {'U','D','L','R','.'};

template <class T>
static inline bool setmin(T& a, const T& b){ if(a > b){ a = b; return true; } return false; }

// =======================================================
// Minimal ChaCha20 RNG (to match rand_chacha::ChaCha20Rng)
// =======================================================
// Notes:
// - rand_chacha::ChaCha20Rng uses ChaCha20 with a 32-byte key derived from seed.
// - To be strictly identical, you must replicate rand_chacha seeding exactly.
// - The following is a practical translation that behaves like a ChaCha20 stream RNG
//   seeded from u64. For strict byte-for-byte match with rand_chacha, you may need
//   to mirror its SeedableRng derivation (SplitMix64 into 32 bytes, etc.).
//
// If you only need "a working local tester", you can replace this whole RNG with mt19937_64.
// =======================================================

struct SplitMix64 {
    uint64_t x;
    explicit SplitMix64(uint64_t seed): x(seed) {}
    uint64_t next() {
        uint64_t z = (x += 0x9E3779B97F4A7C15ULL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }
};

// ChaCha20 core
static inline uint32_t rotl32(uint32_t x, int r){ return (x << r) | (x >> (32 - r)); }
static inline void quarterround(uint32_t& a, uint32_t& b, uint32_t& c, uint32_t& d){
    a += b; d ^= a; d = rotl32(d,16);
    c += d; b ^= c; b = rotl32(b,12);
    a += b; d ^= a; d = rotl32(d, 8);
    c += d; b ^= c; b = rotl32(b, 7);
}

struct ChaCha20 {
    array<uint32_t,16> state{};
    uint32_t counter = 0;
    array<uint8_t,64> block{};
    int idx = 64; // consumed

    static uint32_t le32(const uint8_t* p){
        return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
    }
    static void store32(uint8_t* p, uint32_t v){
        p[0] = (uint8_t)(v & 0xFF);
        p[1] = (uint8_t)((v >> 8) & 0xFF);
        p[2] = (uint8_t)((v >> 16) & 0xFF);
        p[3] = (uint8_t)((v >> 24) & 0xFF);
    }

    void init_from_seed_u64(uint64_t seed){
        // Derive 32-byte key using SplitMix64 (matches many SeedableRng patterns).
        SplitMix64 sm(seed);
        array<uint8_t,32> key{};
        for(int i=0;i<4;i++){
            uint64_t v = sm.next();
            for(int j=0;j<8;j++) key[i*8+j] = (uint8_t)((v >> (8*j)) & 0xFF);
        }

        // constants "expand 32-byte k"
        state[0] = 0x61707865;
        state[1] = 0x3320646e;
        state[2] = 0x79622d32;
        state[3] = 0x6b206574;
        // key
        for(int i=0;i<8;i++){
            state[4+i] = le32(&key[i*4]);
        }
        // counter and nonce (use 0 nonce)
        state[12] = 0; // counter
        state[13] = 0;
        state[14] = 0;
        state[15] = 0;
        counter = 0;
        idx = 64;
    }

    void refill(){
        array<uint32_t,16> x = state;
        x[12] = counter;
        // 20 rounds
        for(int i=0;i<10;i++){
            // column
            quarterround(x[0], x[4], x[8],  x[12]);
            quarterround(x[1], x[5], x[9],  x[13]);
            quarterround(x[2], x[6], x[10], x[14]);
            quarterround(x[3], x[7], x[11], x[15]);
            // diagonal
            quarterround(x[0], x[5], x[10], x[15]);
            quarterround(x[1], x[6], x[11], x[12]);
            quarterround(x[2], x[7], x[8],  x[13]);
            quarterround(x[3], x[4], x[9],  x[14]);
        }
        // add original
        for(int i=0;i<16;i++){
            uint32_t out = x[i] + (i==12 ? counter : state[i]);
            store32(&block[i*4], out);
        }
        counter++;
        idx = 0;
    }

    uint32_t next_u32(){
        if(idx >= 64) refill();
        uint32_t v = le32(&block[idx]);
        idx += 4;
        return v;
    }

    uint64_t next_u64(){
        uint64_t a = (uint64_t)next_u32();
        uint64_t b = (uint64_t)next_u32();
        return a | (b << 32);
    }
};

// uniform choice from vector using RNG
template <class T>
static inline const T& choose_one(const vector<T>& v, ChaCha20& rng){
    uint64_t r = rng.next_u64();
    size_t idx = (size_t)(r % v.size());
    return v[idx];
}

// =======================================================
// Input / parsing (like Rust parse_input + Display)
// =======================================================

struct Input {
    vector<tuple<size_t,size_t,size_t>> ps;
    vector<pair<size_t,size_t>> hs;
    uint64_t seed;
};

static Input parse_input_all_stdin(){
    // Rust reads the entire stdin to string and then parses.
    // We parse directly as tokens.
    Input in;
    int N; 
    if(!(cin >> N)) {
        throw runtime_error("failed to read input");
    }
    in.ps.reserve(N);
    for(int i=0;i<N;i++){
        size_t x,y,t; cin >> x >> y >> t;
        in.ps.emplace_back(x-1, y-1, t);
    }
    int M; cin >> M;
    in.hs.reserve(M);
    for(int i=0;i<M;i++){
        size_t x,y; cin >> x >> y;
        in.hs.emplace_back(x-1, y-1);
    }
    cin >> in.seed;
    return in;
}

static void write_initial_state(ostream& os, const Input& in){
    os << in.ps.size() << "\n";
    for(auto [x,y,t] : in.ps){
        os << (x+1) << " " << (y+1) << " " << t << "\n";
    }
    os << in.hs.size() << "\n";
    for(auto [x,y] : in.hs){
        os << (x+1) << " " << (y+1) << "\n";
    }
    os.flush();
}

// =======================================================
// BFS (same as Rust bfs)
// =======================================================

static vector<vector<size_t>> bfs(const vector<vector<bool>>& blocked, size_t sx, size_t sy){
    vector<vector<size_t>> dist(D, vector<size_t>(D, (size_t)-1));
    deque<pair<size_t,size_t>> q;
    q.push_back({sx,sy});
    dist[sx][sy] = 0;
    while(!q.empty()){
        auto [x,y] = q.front(); q.pop_front();
        size_t t = dist[x][y];
        for(int d=0; d<4; d++){
            size_t x2 = x + DIR[d].first;
            size_t y2 = y + DIR[d].second;
            if(x2 < (size_t)D && y2 < (size_t)D && !blocked[x2][y2] && setmin(dist[x2][y2], t+1)){
                q.push_back({x2,y2});
            }
        }
    }
    return dist;
}

// =======================================================
// Pet, Sim (translation of Rust Sim)
// =======================================================

struct Pet {
    enum Kind { Cow, Pig, Rabbit, Dog, Cat } kind;
    size_t a = (size_t)-1;
    size_t b = (size_t)-1;
    static Pet make_cow(){ return Pet{Cow,(size_t)-1,(size_t)-1}; }
    static Pet make_pig(){ return Pet{Pig,(size_t)-1,(size_t)-1}; }
    static Pet make_rabbit(){ return Pet{Rabbit,(size_t)-1,(size_t)-1}; }
    static Pet make_dog(){ return Pet{Dog,(size_t)-1,(size_t)-1}; }        // a = target
    static Pet make_cat(){ return Pet{Cat,(size_t)-1,(size_t)-1}; }        // a,b = tx,ty
};

struct Sim {
    vector<vector<bool>> blocked;
    ChaCha20 rng;
    vector<tuple<size_t,size_t,Pet>> ps;
    vector<pair<size_t,size_t>> hs;
    size_t turn = 0;

    explicit Sim(const Input& input){
        blocked.assign(D, vector<bool>(D,false));
        rng.init_from_seed_u64(input.seed);
        hs = input.hs;
        ps.reserve(input.ps.size());
        for(auto [x,y,t] : input.ps){
            Pet p;
            if(t==1) p = Pet::make_cow();
            else if(t==2) p = Pet::make_pig();
            else if(t==3) p = Pet::make_rabbit();
            else if(t==4) p = Pet::make_dog();
            else if(t==5) p = Pet::make_cat();
            else throw runtime_error("invalid input");
            ps.emplace_back(x,y,p);
        }
    }

    // human_move: returns Ok/Err like Rust
    bool human_move(const string& out, string& err){
        turn += 1;
        if(out.size() != hs.size()){
            err = "illegal output length (turn " + to_string(turn) + ")";
            return false;
        }

        auto new_hs = hs;

        for(size_t i=0;i<out.size();i++){
            char c = out[i];
            if(c=='.') continue;

            if(c>='a' && c<='z'){
                const string dirs = "udlr";
                auto pos = dirs.find(c);
                if(pos == string::npos){
                    err = "illegal output char " + string(1,c) + " (turn " + to_string(turn) + ")";
                    return false;
                }
                int dir = (int)pos;
                size_t x = hs[i].first  + DIR[dir].first;
                size_t y = hs[i].second + DIR[dir].second;
                if(x >= (size_t)D || y >= (size_t)D) continue;

                // cannot block pet
                for(auto &pp: ps){
                    if(get<0>(pp)==x && get<1>(pp)==y){
                        err = "trying to block a square containing a pet (turn " + to_string(turn) + ")";
                        return false;
                    }
                }
                // cannot block human
                for(auto &hh: hs){
                    if(hh.first==x && hh.second==y){
                        err = "trying to block a square containing a human (turn " + to_string(turn) + ")";
                        return false;
                    }
                }
                // cannot block adjacent to a pet
                for(int d=0; d<4; d++){
                    size_t x2 = x + DIR[d].first;
                    size_t y2 = y + DIR[d].second;
                    if(x2 < (size_t)D && y2 < (size_t)D){
                        bool adj_pet = false;
                        for(auto &pp: ps){
                            if(get<0>(pp)==x2 && get<1>(pp)==y2){ adj_pet=true; break; }
                        }
                        if(adj_pet){
                            err = "trying to block a square whose adjacent square contains a pet (turn " + to_string(turn) + ")";
                            return false;
                        }
                    }
                }
                blocked[x][y] = true;
            }
            else if(c>='A' && c<='Z'){
                // DIR_CHAR contains U D L R .
                int dir = -1;
                for(int k=0;k<4;k++) if(DIR_CHAR[k]==c) dir=k;
                if(dir==-1){
                    err = "illegal output char " + string(1,c) + " (turn " + to_string(turn) + ")";
                    return false;
                }
                new_hs[i].first  += DIR[dir].first;
                new_hs[i].second += DIR[dir].second;
                if(new_hs[i].first >= (size_t)D || new_hs[i].second >= (size_t)D){
                    err = "trying to move to an impassible square (turn " + to_string(turn) + ")";
                    return false;
                }
            } else {
                err = "illegal output char " + string(1,c) + " (turn " + to_string(turn) + ")";
                return false;
            }
        }

        hs = new_hs;
        for(auto &h: hs){
            if(blocked[h.first][h.second]){
                err = "trying to move to an impassible square (turn " + to_string(turn) + ")";
                return false;
            }
        }
        return true;
    }

    size_t standard_move(size_t& x, size_t& y){
        vector<size_t> cand;
        for(size_t d=0; d<4; d++){
            size_t x2 = x + DIR[d].first;
            size_t y2 = y + DIR[d].second;
            if(x2 < (size_t)D && y2 < (size_t)D && !blocked[x2][y2]){
                cand.push_back(d);
            }
        }
        // Rust unwrap() expects non-empty
        size_t d = choose_one(cand, rng);
        x += DIR[d].first;
        y += DIR[d].second;
        return d;
    }

    string pet_move(){
        auto ps2 = ps;

        vector<string> tokens;
        tokens.reserve(ps2.size());

        for(auto &pp : ps2){
            size_t &x = get<0>(pp);
            size_t &y = get<1>(pp);
            Pet &pet = get<2>(pp);

            auto emit_basic = [&](int steps)->string{
                string s;
                for(int k=0;k<steps;k++){
                    size_t d = standard_move(x,y);
                    s.push_back(DIR_CHAR[d]);
                }
                return s;
            };

            if(pet.kind == Pet::Cow){
                tokens.push_back(emit_basic(1));
            } else if(pet.kind == Pet::Pig){
                tokens.push_back(emit_basic(2));
            } else if(pet.kind == Pet::Rabbit){
                tokens.push_back(emit_basic(3));
            } else if(pet.kind == Pet::Dog){
                size_t &target = pet.a;
                while(true){
                    if(target == (size_t)-1 || hs[target] == make_pair(x,y)){
                        auto dist = bfs(blocked, x, y);
                        vector<size_t> cand;
                        for(size_t i=0;i<hs.size();i++){
                            auto [hx,hy] = hs[i];
                            if(dist[hx][hy] != (size_t)-1 && dist[hx][hy] > 0) cand.push_back(i);
                        }
                        if(!cand.empty()){
                            target = choose_one(cand, rng);
                        } else {
                            target = (size_t)-1;
                            string s;
                            s.push_back(DIR_CHAR[standard_move(x,y)]);
                            tokens.push_back(s);
                            break;
                        }
                    }
                    auto [tx,ty] = hs[target];
                    auto dist = bfs(blocked, tx, ty);
                    if(dist[x][y] == (size_t)-1){
                        target = (size_t)-1;
                        continue;
                    }
                    vector<size_t> cand;
                    for(size_t d=0; d<4; d++){
                        size_t x2 = x + DIR[d].first;
                        size_t y2 = y + DIR[d].second;
                        if(x2 < (size_t)D && y2 < (size_t)D && dist[x][y] > dist[x2][y2]){
                            cand.push_back(d);
                        }
                    }
                    size_t dir = choose_one(cand, rng);
                    x += DIR[dir].first;
                    y += DIR[dir].second;
                    if(hs[target] == make_pair(x,y)) target = (size_t)-1;

                    string s;
                    s.push_back(DIR_CHAR[dir]);
                    s.push_back(DIR_CHAR[standard_move(x,y)]);
                    if(target != (size_t)-1 && hs[target] == make_pair(x,y)) target = (size_t)-1;
                    tokens.push_back(s);
                    break;
                }
            } else if(pet.kind == Pet::Cat){
                size_t &tx = pet.a;
                size_t &ty = pet.b;
                while(true){
                    if(tx != (size_t)-1 && blocked[tx][ty]){
                        tx = ty = (size_t)-1;
                    }
                    if(tx == (size_t)-1){
                        auto dist = bfs(blocked, x, y);
                        vector<pair<size_t,size_t>> cand;
                        for(size_t i=0;i<(size_t)D;i++){
                            for(size_t j=0;j<(size_t)D;j++){
                                if(dist[i][j] != (size_t)-1 && dist[i][j] > 0) cand.push_back({i,j});
                            }
                        }
                        auto pr = choose_one(cand, rng);
                        tx = pr.first; ty = pr.second;
                    }
                    auto dist = bfs(blocked, tx, ty);
                    if(dist[x][y] == (size_t)-1){
                        tx = ty = (size_t)-1;
                        continue;
                    }
                    vector<size_t> cand;
                    for(size_t d=0; d<4; d++){
                        size_t x2 = x + DIR[d].first;
                        size_t y2 = y + DIR[d].second;
                        if(x2 < (size_t)D && y2 < (size_t)D && dist[x][y] > dist[x2][y2]){
                            cand.push_back(d);
                        }
                    }
                    size_t dir = choose_one(cand, rng);
                    x += DIR[dir].first;
                    y += DIR[dir].second;
                    if(make_pair(tx,ty) == make_pair(x,y)) tx = ty = (size_t)-1;

                    string s;
                    s.push_back(DIR_CHAR[dir]);
                    s.push_back(DIR_CHAR[standard_move(x,y)]);
                    if(make_pair(tx,ty) == make_pair(x,y)) tx = ty = (size_t)-1;
                    tokens.push_back(s);
                    break;
                }
            }
        }

        ps = ps2;

        // join tokens by space
        string out;
        for(size_t i=0;i<tokens.size();i++){
            if(i) out.push_back(' ');
            out += tokens[i];
        }
        return out;
    }

    long long compute_score() const {
        double score = 0.0;
        for(auto [x,y] : hs){
            auto dist = bfs(blocked, x, y);
            int r = 0;
            for(int i=0;i<D;i++) for(int j=0;j<D;j++){
                if(dist[i][j] != (size_t)-1) r++;
            }
            int n = 0;
            for(auto &pp : ps){
                auto px = (int)get<0>(pp);
                auto py = (int)get<1>(pp);
                if(dist[px][py] != (size_t)-1) n++;
            }
            score += (double)r / (30.0*30.0) * pow(2.0, -n);
        }
        return (long long)llround(1e8 * score / (double)hs.size());
    }
};

// =======================================================
// Child process I/O helper (POSIX popen-style using pipes)
// For simplicity, this version uses fork/exec on POSIX.
// If you are on Windows, you’ll need a different implementation.
// =======================================================

#ifdef _WIN32
#error "This example uses POSIX fork/exec. Use CreateProcess on Windows."
#endif

#include <unistd.h>
#include <sys/wait.h>

struct Child {
    pid_t pid = -1;
    int in_fd = -1;   // write to child stdin
    int out_fd = -1;  // read from child stdout
};

static Child spawn_child(const vector<string>& cmd){
    int in_pipe[2], out_pipe[2];
    if(pipe(in_pipe) != 0) throw runtime_error("pipe() failed");
    if(pipe(out_pipe) != 0) throw runtime_error("pipe() failed");

    pid_t pid = fork();
    if(pid < 0) throw runtime_error("fork() failed");

    if(pid == 0){
        // child
        dup2(in_pipe[0], STDIN_FILENO);
        dup2(out_pipe[1], STDOUT_FILENO);
        // close
        close(in_pipe[0]); close(in_pipe[1]);
        close(out_pipe[0]); close(out_pipe[1]);

        vector<char*> argv;
        argv.reserve(cmd.size()+1);
        for(auto& s: cmd) argv.push_back(const_cast<char*>(s.c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        _exit(1);
    }

    // parent
    close(in_pipe[0]);
    close(out_pipe[1]);
    Child c;
    c.pid = pid;
    c.in_fd = in_pipe[1];
    c.out_fd = out_pipe[0];
    return c;
}

static bool read_line_child(int fd, string& line){
    line.clear();
    char ch;
    while(true){
        ssize_t r = ::read(fd, &ch, 1);
        if(r == 0) return false;     // EOF
        if(r < 0) return false;
        if(ch == '\n') break;
        line.push_back(ch);
    }
    return true;
}

static void write_all(int fd, const string& s){
    const char* p = s.c_str();
    size_t n = s.size();
    while(n){
        ssize_t w = ::write(fd, p, n);
        if(w <= 0) throw runtime_error("write failed");
        p += w;
        n -= (size_t)w;
    }
}

// Like Rust read_line(stdout, local): skip empty/# lines, echo if local.
static bool solver_read_move(int out_fd, bool local, string& out_move, string& err){
    while(true){
        string line;
        if(!read_line_child(out_fd, line)){
            err = "Your program has terminated unexpectedly";
            return false;
        }
        if(local){
            // emulate Rust `print!("{}", out);`
            cout << line << "\n";
            cout.flush();
        }
        string v = line;
        // trim
        auto l = v.find_first_not_of(" \t\r");
        auto r = v.find_last_not_of(" \t\r");
        if(l == string::npos) v.clear();
        else v = v.substr(l, r-l+1);

        if(v.empty() || (!v.empty() && v[0] == '#')) continue;
        out_move = v;
        return true;
    }
}

static long long exec_like_rust(const vector<string>& cmd, bool local){
    Input input = parse_input_all_stdin();
    Sim sim(input);

    Child child = spawn_child(cmd);

    // send initial state WITHOUT seed (exactly like Rust Display)
    {
        ostringstream oss;
        write_initial_state(oss, input);
        write_all(child.in_fd, oss.str());
    }

    for(int turn=1; turn<=T; turn++){
        string out, err;
        if(!solver_read_move(child.out_fd, local, out, err)){
            throw runtime_error(err);
        }
        string sim_err;
        if(!sim.human_move(out, sim_err)){
            throw runtime_error(sim_err);
        }
        string pet = sim.pet_move();
        write_all(child.in_fd, pet + "\n");
    }

    // wait child
    int status = 0;
    waitpid(child.pid, &status, 0);

    return sim.compute_score();
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // -------- read input from inf --------
    Input in;
    int Npets = inf.readInt();
    in.ps.resize(Npets);
    for (int i = 0; i < Npets; i++) {
        int x = inf.readInt();
        int y = inf.readInt();
        int t = inf.readInt();
        in.ps[i] = { (size_t)(x - 1), (size_t)(y - 1), (size_t)t };
    }
    int Mhum = inf.readInt();
    in.hs.resize(Mhum);
    for (int i = 0; i < Mhum; i++) {
        int x = inf.readInt();
        int y = inf.readInt();
        in.hs[i] = { (size_t)(x - 1), (size_t)(y - 1) };
    }
    in.seed = inf.readUnsignedLong();

    // -------- send initial state to participant (no seed) --------
    cout << Npets << "\n";
    for (auto &[x, y, t] : in.ps) {
        cout << (x + 1) << " " << (y + 1) << " " << t << "\n";
    }
    cout << Mhum << "\n";
    for (auto &h : in.hs) {
        cout << (h.first + 1) << " " << (h.second + 1) << "\n";
    }
    cout.flush();

    Sim sim(in);

    auto trim_str_all_cpp = [](const string &s) -> string {
        size_t l = 0, r = s.size();
        while (l < r && isspace((unsigned char)s[l])) l++;
        while (r > l && isspace((unsigned char)s[r - 1])) r--;
        return s.substr(l, r - l);
    };

    // -------- interaction loop --------
    for (int t = 1; t <= T; t++) {
        string line;

        // Read one action line (skip empty/#), fail cleanly at EOF like reference.
        while (true) {
            if (ouf.seekEof()) {
                quitf(_wa, "participant terminated early at turn %d", t);
            }
            line = ouf.readLine();
            line = trim_str_all_cpp(line);
            if (line.empty()) continue;
            if (!line.empty() && line[0] == '#') continue;
            break;
        }

        // Apply human move (validate)
        string sim_err;
        if (!sim.human_move(line, sim_err)) {
            quitf(_wa, "%s", sim_err.c_str());
        }

        // Compute pet move and send to participant
        string pet_mv = sim.pet_move();
        cout << pet_mv << "\n";
        cout.flush();
    }

    // -------- scoring --------
    long long score = sim.compute_score();

    long long baseline_value = ans.readLong();
    long long best_value     = ans.readLong();

    double score_ratio;
    if (best_value == baseline_value) {
        score_ratio = (score >= best_value ? 1.0 : 0.0);
    } else {
        score_ratio = (double)(score - baseline_value) / (double)(best_value - baseline_value);
        if (score_ratio < 0.0) score_ratio = 0.0;
        if (score_ratio > 1.0) score_ratio = 1.0;
    }

    double ratio_unbounded = (double)(score - baseline_value) / (double)(best_value - baseline_value);
    if (ratio_unbounded < 0.0) ratio_unbounded = 0.0;
    quitp(score_ratio, "Value: %lld. Ratio: %.6f. RatioUnbounded: %.6f", score, score_ratio, ratio_unbounded);
    return 0;
}

