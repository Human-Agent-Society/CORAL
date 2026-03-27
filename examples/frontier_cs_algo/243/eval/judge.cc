#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <algorithm>

using namespace std;

// Directions: 0: N, 1: E, 2: S, 3: W
const int DR[] = {-1, 0, 1, 0};
const int DC[] = {0, 1, 0, -1};

int R, C;
vector<string> grid;
int trueR, trueC, trueDir;

// Check if position (r, c) is valid (within bounds and is empty cell)
bool isValid(int r, int c) {
    return r >= 0 && r < R && c >= 0 && c < C && grid[r][c] == '.';
}

// Calculate distance to wall in the given direction
int getDistanceToWall(int r, int c, int dir) {
    int dist = 0;
    int nr = r + DR[dir];
    int nc = c + DC[dir];
    while (isValid(nr, nc)) {
        dist++;
        nr += DR[dir];
        nc += DC[dir];
    }
    return dist;
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);
    
    // Read input
    R = inf.readInt();
    C = inf.readInt();
    inf.readEoln();  // Skip end of line
    
    grid.resize(R);
    for (int i = 0; i < R; i++) {
        grid[i] = inf.readToken();
    }
    
    trueR = inf.readInt() - 1;  // Convert to 0-based index
    trueC = inf.readInt() - 1;  // Convert to 0-based index
    trueDir = inf.readInt();
    
    // Validate hidden start position
    if (!isValid(trueR, trueC)) {
        quitf(_fail, "Hidden start position (%d, %d) is invalid!", trueR + 1, trueC + 1);
    }
    
    // Read standard answer
    string res = ans.readToken();  // "yes" or "no"
    int stdSteps = ans.readInt();  // Standard number of steps
    
    // Output initial grid to participant
    cout << R << " " << C << endl;
    for (int i = 0; i < R; i++) {
        cout << grid[i] << endl;
    }
    cout.flush();
    
    // Initialize current position and direction
    int curR = trueR;
    int curC = trueC;
    int curDir = trueDir;
    
    // Participant's step counter
    int userSteps = 0;
    
    // Interaction loop: allow up to 2 * stdSteps steps
    while (userSteps <= 2 * stdSteps) {
        // Output distance to wall in current direction
        cout << getDistanceToWall(curR, curC, curDir) << endl;
        cout.flush();
        
        // Read participant's command
        string cmd = ouf.readToken();
        userSteps++;  // Each command counts as one step (including final "yes"/"no")
        
        if (cmd == "left") {
            // Turn left (counterclockwise)
            curDir = (curDir + 3) % 4;
        } else if (cmd == "right") {
            // Turn right (clockwise)
            curDir = (curDir + 1) % 4;
        } else if (cmd == "step") {
            // Move one step forward
            int nr = curR + DR[curDir];
            int nc = curC + DC[curDir];
            if (!isValid(nr, nc)) {
                // Crashed into wall
                cout << -1 << endl;
                cout.flush();
                double score_ratio = 0.0;
                double unbounded_ratio = 0.0;
                quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Round %d: Crashed into wall at (%d, %d)", 
                      userSteps, score_ratio, unbounded_ratio, userSteps, curR + 1, curC + 1);
            }
            curR = nr;
            curC = nc;
        } else if (cmd == "yes" || cmd == "no") {
            // Participant claims to have found the position or determined it's impossible
            // Calculate score based on number of steps
            // Ensure denominator is not zero (handle edge case where stdSteps is 0)
            if (stdSteps <= 0) stdSteps = 1;
            
            double score_ratio = 0.0;
            double unbounded_ratio = 0.0;
            string msg;
            
            if (userSteps <= stdSteps) {
                score_ratio = 1.0;  // Perfect or better than standard
                unbounded_ratio = 1.0;
                msg = "Perfect!";
            } else if (userSteps >= 2 * stdSteps) {
                score_ratio = 0.0;  // Too slow
                unbounded_ratio = 0.0;
                msg = "Too slow.";
            } else {
                // Linear interpolation: score decreases from 1.0 to 0.0 as steps increase from stdSteps to 2*stdSteps
                // Formula: (2*stdSteps - userSteps) / stdSteps
                score_ratio = (double)(2 * stdSteps - userSteps) / (double)stdSteps;
                unbounded_ratio = score_ratio;
                msg = "Suboptimal.";
            }
            
            // Ensure score is in [0.0, 1.0]
            score_ratio = max(0.0, min(1.0, score_ratio));
            unbounded_ratio = max(0.0, min(1.0, unbounded_ratio));
            
            if (cmd == "yes") {
                // Participant claims solution exists, read guessed position
                int guessR = ouf.readInt();
                int guessC = ouf.readInt();
                
                cout << -1 << endl;
                cout.flush();
                
                if (res != "yes") {
                    // Standard answer says "no" but participant says "yes"
                    double error_score = 0.0;
                    double error_unbounded = 0.0;
                    quitp(error_score, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Standard answer is 'no' but you output 'yes'.", 
                          userSteps, error_score, error_unbounded);
                } else if (guessR - 1 == curR && guessC - 1 == curC) {
                    // Correct guess
                    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. %s UserSteps=%d, StdSteps=%d", 
                          userSteps, score_ratio, unbounded_ratio, msg.c_str(), userSteps, stdSteps);
                } else {
                    // Wrong position guessed
                    double error_score = 0.0;
                    double error_unbounded = 0.0;
                    quitp(error_score, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Wrong position guessed. At (%d, %d), guessed (%d, %d)", 
                          userSteps, error_score, error_unbounded, curR + 1, curC + 1, guessR, guessC);
                }
            } else if (cmd == "no") {
                // Participant claims no solution exists
                cout << -1 << endl;
                cout.flush();
                
                if (res != "no") {
                    // Standard answer says "yes" but participant says "no"
                    double error_score = 0.0;
                    double error_unbounded = 0.0;
                    quitp(error_score, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Standard answer is 'yes' but you output 'no'.", 
                          userSteps, error_score, error_unbounded);
                } else {
                    // Correct: no solution exists
                    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. %s UserSteps=%d, StdSteps=%d", 
                          userSteps, score_ratio, unbounded_ratio, msg.c_str(), userSteps, stdSteps);
                }
            }
        } else {
            // Invalid command
            cout << -1 << endl;
            cout.flush();
            double score_ratio = 0.0;
            double unbounded_ratio = 0.0;
            quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Invalid command: %s", 
                  userSteps, score_ratio, unbounded_ratio, cmd.c_str());
        }
    }
    
    // Exceeded maximum allowed steps
    cout << -1 << endl;
    cout.flush();
    double score_ratio = 0.0;
    double unbounded_ratio = 0.0;
    quitp(score_ratio, "Value: %d. Ratio: %.4f, RatioUnbounded: %.4f. Exceeded maximum allowed steps (2 * StdSteps = %d)", 
          userSteps, score_ratio, unbounded_ratio, 2 * stdSteps);
    
    return 0;
}
