#include "testlib.h"
#include <chrono>
#include <vector>
#include <string>

#ifdef _WIN32
#include <process.h> // _getpid()
#else
#include <unistd.h>  // getpid()
#endif

using namespace std;

struct LiarScheduler {
    bool lastWasLie = false;
    int pTruthPermille;                 // 0..1000
    explicit LiarScheduler(int p = 500) : pTruthPermille(p) {}
    bool nextTruth() {
        if (lastWasLie) { lastWasLie = false; return true; }
        int r = rnd.next(0, 999);
        bool truth = (r < pTruthPermille);
        lastWasLie = !truth;
        return truth;
    }
};

int main(int argc, char* argv[]) {
    setName("Liar game interactor");
    registerInteraction(argc, argv);

    // Public input (from tests)
    int n = inf.readInt(1, 100000, "n");

    // .ans format: EXACTLY TWO TOKENS:
    //   1) best_queries (nonnegative, used for scoring)
    //   2) hidden_x  (in [1..n])
    long long best_queries = ans.readLong();
    int hidden_x = ans.readInt(1, n, "hidden_x");

    // Seed rnd deterministically enough (no optional controls)
    unsigned long long seed =
            (unsigned long long)chrono::steady_clock::now().time_since_epoch().count();
#ifdef _WIN32
    seed ^= (unsigned long long)_getpid();
#else
    seed ^= (unsigned long long)getpid();
#endif
    rnd.setSeed((long long)seed);

    // Send n to the participant and FLUSH.
    cout << n << endl;

    LiarScheduler liar(500); // 50% truth

    const int MAX_QUESTIONS = 53; // counts only '?'
    const int MAX_GUESSES   = 2;

    long long question_count = 0;
    int guess_count = 0;

    while (true) {
        // Read the next action: must be "?" or "!"
        string action = ouf.readToken(); // token (skips spaces/newlines)
        if (action != "?" && action != "!") {
            quitf(_wa, "Invalid action '%s': expected '?' or '!'.", action.c_str());
        }

        if (action == "?") {
            int k = ouf.readInt(1, n, "k");
            vector<int> S(k);
            vector<char> inSet(n + 1, 0);
            for (int i = 0; i < k; ++i) {
                S[i] = ouf.readInt(1, n, "S[i]");
                if (inSet[S[i]]) quitf(_wa, "Invalid query: duplicate element %d.", S[i]);
                inSet[S[i]] = 1;
            }

            ++question_count;
            if (question_count > MAX_QUESTIONS) {
                quitp(0.0,
                      "Query limit exceeded: used %lld (> %d). Ratio: 0.0000",
                      question_count, MAX_QUESTIONS);
            }

            bool actual = (inSet[hidden_x] != 0);
            bool truthful = liar.nextTruth();
            bool replyYes = truthful ? actual : !actual;

            // Answer and FLUSH
            cout << (replyYes ? "YES" : "NO") << endl;

        } else { // action == "!"
            int g = ouf.readInt(1, n, "guess");
            ++guess_count;
            if (guess_count > MAX_GUESSES) {
                quitp(0.0, "Guess limit exceeded. Max guesses: %d. Ratio: 0.0000", MAX_GUESSES);
            }

            if (g == hidden_x) {
                cout << ":)" << endl;

                long long your_queries = question_count; // guesses DO NOT count
                if (your_queries > MAX_QUESTIONS) {
                    quitp(0.0,
                          "Correct guess, but exceeded %d questions. Questions used: %lld. Ratio: 0.0000",
                          MAX_QUESTIONS, your_queries);
                }

                double your_value = double(MAX_QUESTIONS - your_queries);
                double best_value = double(MAX_QUESTIONS - best_queries);

                if (best_value <= your_value) {
                    quitp(1.0, "Correct guess with %lld questions. Exceeded expectations. Ratio: 1.0000",
                          your_queries);
                }

                double score_ratio = your_value / best_value;
                if (score_ratio < 0.0) score_ratio = 0.0;
                double unbounded_ratio = max(0.0, score_ratio);
                if (score_ratio > 1.0) score_ratio = 1.0;

                quitp(score_ratio, "Correct guess in %lld questions. Ratio: %.4f, RatioUnbounded: %.4f",
                      your_queries, score_ratio, unbounded_ratio);
            } else {
                cout << ":(" << endl;
                if (guess_count == MAX_GUESSES) {
                    quitp(0.0, "Wrong guess. Ratio: 0.0000");
                }
            }
        }
    }
}
