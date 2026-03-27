#include "testlib.h"
#include <bits/stdc++.h>
using namespace std;

struct Card {
    int color, value;
    Card(): color(-1), value(-1) {}
    Card(int _color, int _value): color(_color), value(_value) {}
};

struct State {
    Card alice[2], bob[2];
    Card community[5];
};

enum class ActionType {
    CHECK, CALL, RAISE, FOLD
};

namespace {

// hand evaluation
enum class HandType {
    StraightFlush = 8,
    Four = 7,
    FullHouse = 6,
    Flush = 5,
    Straight = 4,
    Three = 3,
    TwoPair = 2,
    Pair = 1,
    HighCard = 0
};

struct Score {
    HandType w;
    int hash_value;
    Score() : w(HandType::HighCard), hash_value(0) {}
    Score(HandType _w, vector<int>& A) {
        w = _w; hash_value = 0;
        for (int i = 0; i < (int)A.size(); ++i) {
            hash_value = hash_value * 20 + A[i];
        }
    }
};

bool operator<(const Score& k1, const Score& k2) {
    if (k1.w != k2.w) return k1.w < k2.w;
    return k1.hash_value < k2.hash_value;
}

struct CardCmp {
    bool operator () (const Card& x, const Card& y) const {
        return x.value < y.value || (x.value == y.value && x.color < y.color);
    }
};

bool is_card_used[14][5];
int used_num[14];

bool isValidCard(const Card& card) {
    return 1 <= card.value && card.value <= 13 && 0 <= card.color && card.color <= 3;
}

void assertCompleteStateOrFail(const State& s) {
    static set<Card, CardCmp> S;
    S.clear();
    for (int i = 0; i < 2; ++i) {
        ensuref(isValidCard(s.alice[i]), "Internal error: invalid Alice card in complete state");
        ensuref(S.find(s.alice[i]) == S.end(), "Internal error: duplicate card in complete state");
        S.insert(s.alice[i]);
        ensuref(isValidCard(s.bob[i]), "Internal error: invalid Bob card in complete state");
        ensuref(S.find(s.bob[i]) == S.end(), "Internal error: duplicate card in complete state");
        S.insert(s.bob[i]);
    }
    for (int i = 0; i < 5; ++i) {
        ensuref(isValidCard(s.community[i]), "Internal error: invalid community card in complete state");
        ensuref(S.find(s.community[i]) == S.end(), "Internal error: duplicate card in complete state");
        S.insert(s.community[i]);
    }
}

// forward rngs
mt19937_64 rng_sampling; // for RATE queries and BobAction sampling

bool checkStraightFlush(Score& res) {
    for (int c = 0; c < 4; ++c) {
        for (int i = 9; i >= 0; --i) {
            int flag = 0;
            for (int j = 0; j <= 4; ++j)
                if (!is_card_used[i + j][c]) {
                    flag = 1;
                    break;
                }
            if (flag) continue;
            vector<int> A;
            for (int j = 4; j >= 0; j--) A.push_back(i + j);
            res = Score(HandType::StraightFlush, A);
            return true;
        }
    }
    return false;
}

bool checkFour(Score& res) {
    for (int i = 13; i; i--)
        if (used_num[i] == 4) {
            vector<int> A;
            for (int k = 0; k < 4; k++) A.push_back(i);
            for (int j = 13; j; j--)
                if (i != j && used_num[j]) {
                    A.push_back(j);
                    res = Score(HandType::Four, A);
                    return true;
                }
        }
    return false;
}

bool checkFullHouse(Score &res) {
    for (int i = 13; i; i--)
        if (used_num[i] == 3) {
            vector<int> A;
            for (int k = 0; k < 3; k++) A.push_back(i);
            for (int j = 13; j; j--)
                if (i != j && used_num[j] >= 2) {
                    for (int k = 0; k < 2; k++) A.push_back(j);
                    res = Score(HandType::FullHouse, A);
                    return true;
                }
        }
    return false;
}

bool checkFlush(Score &res) {
    for (int c = 0; c < 4; c++) {
        vector<int> A;
        for (int i = 13; i; i--)
            if (is_card_used[i][c]) {
                A.push_back(i);
                if ((int)A.size() == 5) {
                    res = Score(HandType::Flush, A);
                    return true;
                }
            }
    }
    return false;
}

bool checkStraight(Score &res) {
    for (int i = 9; i >= 0; i--) {
        int flag = 0;
        for (int j = 4; j >= 0; j--)
            if (!used_num[i + j]) {
                flag = 1;
                break;
            }
        if (flag) continue;
        vector<int> A;
        for (int j = 4; j >= 0; j--)
            A.push_back(i + j);
        res = Score(HandType::Straight, A);
        return true;
    }
    return false;
}

bool checkThree(Score &res) {
    for (int i = 13; i; i--)
        if (used_num[i] >= 3) {
            vector<int> A;
            for (int k = 0; k < 3; k++) A.push_back(i);
            for (int j = 13; j; j--)
                if (used_num[j] && j != i) {
                    A.push_back(j);
                    if ((int)A.size() == 5) {
                        res = Score(HandType::Three, A);
                        return true;
                    }
                }
        }
    return false;
}

bool checkTwoPair(Score &res) {
    for (int i = 13; i; i--)
        if (used_num[i] >= 2) {
            vector<int> A;
            for (int k = 0; k < 2; k++) A.push_back(i);
            for (int j = i - 1; j; j--)
                if (used_num[j] >= 2) {
                    for (int k = 0; k < 2; k++) A.push_back(j);
                    for (int x = 13; x; x--)
                        if (used_num[x] && x != i && x != j) {
                            A.push_back(x);
                            res = Score(HandType::TwoPair, A);
                            return true;
                        }
                }
        }
    return false;
}

bool checkPair(Score &res) {
    for (int i = 13; i; i--)
        if (used_num[i] >= 2) {
            vector<int> A;
            for (int k = 0; k < 2; k++) A.push_back(i);
            for (int j = 13; j; j--)
                if (used_num[j] && j != i) {
                    A.push_back(j);
                    if ((int)A.size() == 5) {
                        res = Score(HandType::Pair, A);
                        return true;
                    }
                }
        }
    return false;
}

void getHighCard(Score &res) {
    vector<int> A;
    for (int i = 13; i; i--)
        if (used_num[i]) {
            A.push_back(i);
            if ((int)A.size() == 5) {
                res = Score(HandType::HighCard, A);
                return;
            }
        }
}

Score getScoreForHand(vector<Card>& A) {
    memset(is_card_used, 0x00, sizeof is_card_used);
    memset(used_num, 0x00, sizeof used_num);
    for (int i = 0; i < (int)A.size(); ++i) {
        is_card_used[A[i].value][A[i].color] = true;
        ++used_num[A[i].value];
    }
    used_num[0] = used_num[13];
    for (int i = 0; i <= 4; i++) {
        is_card_used[0][i] = is_card_used[13][i];
    }
    Score res;
    if (checkStraightFlush(res)) return res;
    if (checkFour(res)) return res;
    if (checkFullHouse(res)) return res;
    if (checkFlush(res)) return res;
    if (checkStraight(res)) return res;
    if (checkThree(res)) return res;
    if (checkTwoPair(res)) return res;
    if (checkPair(res)) return res;
    getHighCard(res);
    return res;
}

int getResult(const State& s) {
    vector<Card> alice, bob;
    assertCompleteStateOrFail(s);
    for (int i = 0; i < 2; ++i) {
        alice.push_back(s.alice[i]);
        bob.push_back(s.bob[i]);
    }
    for (int i = 0; i < 5; ++i) {
        alice.push_back(s.community[i]);
        bob.push_back(s.community[i]);
    }
    Score alice_score = getScoreForHand(alice);
    Score bob_score = getScoreForHand(bob);
    if (alice_score < bob_score) return -1;
    if (bob_score < alice_score) return 1;
    return 0;
}

pair<double, double> getRatesBySampling(const State& s, int t) {
    memset(is_card_used, 0x00, sizeof is_card_used);
    auto deal_with_card = [&](const Card& c) {
        if (isValidCard(c)) {
            ensuref(!is_card_used[c.value][c.color], "Internal error: duplicate card in partial state");
            is_card_used[c.value][c.color] = true;
        }
    };
    for (int i = 0; i < 2; ++i) {
        deal_with_card(s.alice[i]);
        deal_with_card(s.bob[i]);
    }
    for (int i = 0; i < 5; ++i) {
        deal_with_card(s.community[i]);
    }
    vector<Card> remaining_card;
    for (int i = 1; i <= 13; ++i) {
        for (int j = 0; j < 4; ++j) {
            if (!is_card_used[i][j]) {
                remaining_card.emplace_back(j, i);
            }
        }
    }
    int win_num = 0, draw_num = 0;
    for (int _ = 0; _ < t; ++_) {
        State complete_s = s;
        shuffle(remaining_card.begin(), remaining_card.end(), rng_sampling);
        int ind = 0;
        for (int i = 0; i < 2; ++i) {
            if (!isValidCard(s.alice[i])) {
                complete_s.alice[i] = remaining_card[ind++];
            }
            if (!isValidCard(s.bob[i])) {
                complete_s.bob[i] = remaining_card[ind++];
            }
        }
        for (int i = 0; i < 5; ++i) {
            if (!isValidCard(s.community[i])) {
                complete_s.community[i] = remaining_card[ind++];
            }
        }
        auto result = getResult(complete_s);
        if (result == 1) {
            ++win_num;
        } else if (result == 0) {
            ++draw_num;
        }
    }
    return make_pair(1.0 * win_num / t, 1.0 * draw_num / t);
}

State getPartialState(const State& complete_state, int round_index_0based, int player /*0 alice sees, 1 bob sees*/) {
    // round_index_0based: 0 -> preflop (k=0), 1 -> flop (k=3), 2 -> turn (k=4), 3 -> river (k=5)
    int num = 0;
    if (round_index_0based == 0) num = 0;
    else num = 2 + round_index_0based; // 1->3, 2->4, 3->5
    State s = complete_state;
    for (int i = num; i < 5; ++i) {
        s.community[i] = Card();
    }
    if (player == 0) {
        // hide Bob's cards from Alice
        for (int i = 0; i < 2; ++i) {
            s.bob[i] = Card();
        }
    } else {
        // hide Alice's cards from Bob
        for (int i = 0; i < 2; ++i) {
            s.alice[i] = Card();
        }
    }
    return s;
}

pair<ActionType, int> BobAction(const State& s /*partial from Bob's view*/, int rise, int pool_value) {
    pair<double, double> rates = getRatesBySampling(s, 100);
    double w = rates.first, d = rates.second;
    // Bob's expected value if she calls now (relative to current point):
    // win: pool + rise; tie: pool/2; lose: -rise
    double expected_call = -w * rise + d * (pool_value / 2.0) + (1 - w - d) * (pool_value + rise);
    if (expected_call > 0) return make_pair(ActionType::CALL, 0);
    return make_pair(ActionType::FOLD, 0);
}

// helper for formatting/printing doubles
string fmt2(const string& head, double a, double b) {
    ostringstream oss;
    oss.setf(std::ios::fixed); oss<<setprecision(6);
    oss<<head<<" "<<a<<" "<<b;
    return oss.str();
}
string fmt1(const string& head, double a) {
    ostringstream oss;
    oss.setf(std::ios::fixed); oss<<setprecision(6);
    oss<<head<<" "<<a;
    return oss.str();
}

} // namespace

// Generate a full deck order from a seed
vector<Card> generate_deck_from_seed(uint64_t seed) {
    vector<Card> deck;
    deck.reserve(52);
    for (int v = 1; v <= 13; ++v) {
        for (int s = 0; s < 4; ++s) {
            deck.emplace_back(s, v);
        }
    }
    mt19937_64 eng(seed);
    shuffle(deck.begin(), deck.end(), eng);
    // sanity uniqueness
    set<pair<int,int>> S;
    for (auto &c: deck) {
        ensuref(1 <= c.value && c.value <= 13 && 0 <= c.color && c.color <= 3, "Internal error: bad card generated");
        ensuref(S.insert({c.color, c.value}).second, "Internal error: duplicate in generated deck");
    }
    return deck;
}

int compute_points_from_W(double W) {
    // piecewise linear to integer points in [0,100]
    if (W <= 8.0) return 0;
    if (W <= 11.0) {
        double x = 13.3 * (W - 8.0);              // 0 -> 40 over (8,11]
        return (int) llround(x);
    }
    if (W <= 14.0) {
        double x = 40.0 + 14.0 * (W - 11.0);      // 40 -> 82 over (11,14]
        return (int) llround(x);
    }
    if (W <= 20.0) {
        double x = 82.0 + 3.0 * (W - 14.0);       // 82 -> 100 over (14,20]
        return (int) llround(x);
    }
    return 100;
}

double compute_points_unbounded(double W) {
    if (W <= 8.0) return 0.0;
    if (W <= 11.0) {
        double x = 13.3 * (W - 8.0);
        return (double) llround(x);
    }
    if (W <= 14.0) {
        double x = 40.0 + 14.0 * (W - 11.0);
        return (double) llround(x);
    }
    double x = 82.0 + 3.0 * (W - 14.0);
    return (double) llround(x);
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    // Read public G from .in
    int G = inf.readInt();
    println(G); // send G to contestant

    // Read hidden seeds from .ans
    long long sampling_seed = ans.readLong(); // global sampling seed
    int G_ans = ans.readInt();
    ensuref(G_ans >= G, "ANS file has fewer hand seeds (%d) than required hands (%d)", G_ans, G);
    vector<uint64_t> hand_seeds(G_ans);
    for (int i = 0; i < G_ans; ++i) {
        hand_seeds[i] = (uint64_t) ans.readLong();
    }
    rng_sampling.seed((uint64_t)sampling_seed);

    const long long RATE_BUDGET = 3000000LL;
    long long used_rate_budget = 0;

    auto print_state = [&](int h, int r, int a, int b, int P, int k, const State& complete_state) {
        // STATE h r a b P k
        {
            ostringstream oss;
            oss<<"STATE "<<h<<" "<<r<<" "<<a<<" "<<b<<" "<<P<<" "<<k;
            println(oss.str());
        }
        // ALICE c1 v1 c2 v2
        {
            ostringstream oss;
            oss<<"ALICE "<<complete_state.alice[0].color<<" "<<complete_state.alice[0].value<<" "
               <<complete_state.alice[1].color<<" "<<complete_state.alice[1].value;
            println(oss.str());
        }
        // BOARD ...
        {
            ostringstream oss;
            oss<<"BOARD";
            for (int i = 0; i < k; ++i) {
                oss<<" "<<complete_state.community[i].color<<" "<<complete_state.community[i].value;
            }
            println(oss.str());
        }
    };

    auto showdown_delta = [&](int a, int P, const State& complete_state)->int {
        int result = getResult(complete_state);
        if (result == 1) return (a + P) - 100;
        if (result == 0) return (a + P / 2) - 100;
        return a - 100;
    };

    long long total_delta_sum = 0;

    for (int h = 1; h <= G; ++h) {
        // Generate deck for this hand
        vector<Card> deck = generate_deck_from_seed(hand_seeds[h-1]);
        State complete_state;
        // deal: Alice[0..1], Bob[0..1], Community[0..4]
        complete_state.alice[0] = deck[0];
        complete_state.alice[1] = deck[1];
        complete_state.bob[0]   = deck[2];
        complete_state.bob[1]   = deck[3];
        for (int i = 0; i < 5; ++i) {
            complete_state.community[i] = deck[4 + i];
        }

        int a = 100, b = 100, P = 10;
        bool hand_ended = false;

        for (int r = 1; r <= 4 && !hand_ended; ++r) {
            int k = 0;
            if (r == 1) k = 0;
            else if (r == 2) k = 3;
            else if (r == 3) k = 4;
            else if (r == 4) k = 5;

            // send state
            print_state(h, r, a, b, P, k, complete_state);

            // handle RATE queries and then one ACTION
            while (true) {
                string cmd = ouf.readToken();
                if (cmd == "-1") {
                    quitp(0.0, "Contestant terminated with -1");
                } else if (cmd == "RATE") {
                    long long t = ouf.readLong(1, (long long)1e9);
                    if (used_rate_budget + t > RATE_BUDGET) {
                        println("-1");
                        quitp(0.0, "RATE budget exceeded. Used %lld, requested %lld, budget %lld",
                              used_rate_budget, t, RATE_BUDGET);
                    }
                    State partial_for_alice = getPartialState(complete_state, r - 1, 0);
                    auto rates = getRatesBySampling(partial_for_alice, (int)t);
                    used_rate_budget += t;
                    println(fmt2("RATES", rates.first, rates.second));
                } else if (cmd == "ACTION") {
                    string act = ouf.readToken();
                    if (act == "CHECK") {
                        // Bob always checks
                        println("OPP CHECK");
                        if (r == 4) {
                            int delta = showdown_delta(a, P, complete_state);
                            total_delta_sum += delta;
                            {
                                ostringstream oss;
                                oss<<"RESULT "<<delta;
                                println(oss.str());
                            }
                            hand_ended = true;
                        }
                        break;
                    } else if (act == "FOLD") {
                        int delta = a - 100;
                        total_delta_sum += delta;
                        {
                            ostringstream oss;
                            oss<<"RESULT "<<delta;
                            println(oss.str());
                        }
                        hand_ended = true;
                        break;
                    } else if (act == "RAISE") {
                        int x = ouf.readInt();
                        if (x < 1 || x > a) {
                            quitf(_wa, "Invalid RAISE amount x=%d; must be in [1, %d]", x, a);
                        }
                        // Bob decision before updating stacks/pot
                        State bob_view = getPartialState(complete_state, r - 1, 1);
                        auto bob_dec = BobAction(bob_view, x, P);
                        if (bob_dec.first == ActionType::FOLD) {
                            println("OPP FOLD");
                            // If Bob folds, final stack for Alice: a + P (independent of x)
                            int delta = a + P - 100;
                            total_delta_sum += delta;
                            {
                                ostringstream oss;
                                oss<<"RESULT "<<delta;
                                println(oss.str());
                            }
                            hand_ended = true;
                        } else {
                            // CALL
                            println(string("OPP CALL ") + to_string(x));
                            // both invest x, pot + 2x
                            a -= x;
                            b -= x;
                            P += 2 * x;
                            if (r == 4) {
                                int delta = showdown_delta(a, P, complete_state);
                                total_delta_sum += delta;
                                {
                                    ostringstream oss;
                                    oss<<"RESULT "<<delta;
                                    println(oss.str());
                                }
                                hand_ended = true;
                            }
                        }
                        break;
                    } else {
                        quitf(_wa, "Invalid ACTION type: %s", act.c_str());
                    }
                } else {
                    quitf(_wa, "Invalid command before ACTION: %s (expected RATE or ACTION)", cmd.c_str());
                }
            } // end command loop
        } // end rounds
    } // end hands

    double W = (double)total_delta_sum / (double)G;
    println(fmt1("SCORE", W));
    int points = compute_points_from_W(W);
    double ratio = points / 100.0;
    double points_unbounded = compute_points_unbounded(W);
    double ratio_unbounded = points_unbounded / 100.0;
    quitp(ratio, "Average profit W: %.6f, points: %d, Ratio: %.4f, RatioUnbounded: %.4f",
          W, points, ratio, ratio_unbounded);
    return 0;
}
