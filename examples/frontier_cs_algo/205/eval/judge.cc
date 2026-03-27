#include "testlib.h"
#include <vector>
#include <string>
#include <cmath>

using namespace std;

int n;

// Find matching closing parenthesis
int findMatch(const string& s, int pos) {
    if (pos < 0 || pos >= (int)s.length() || s[pos] != '(') {
        return -1;
    }
    int depth = 0;
    for (int i = pos; i < (int)s.length(); i++) {
        if (s[i] == '(') depth++;
        else depth--;
        if (depth == 0) return i;
    }
    return -1;
}

// Extract substring from pos1 to pos2 inclusive
string extract(const string& s, int start, int end) {
    if (start < 0 || end >= (int)s.length() || start > end) return "";
    return s.substr(start, end - start + 1);
}

// Check if string is a valid parenthesis sequence
bool isValid(const string& s) {
    int balance = 0;
    for (char c : s) {
        if (c == '(') balance++;
        else if (c == ')') balance--;
        else return false;
        if (balance < 0) return false;
    }
    return balance == 0;
}

// Try to apply operation 1: p(((A)B)C)q -> p((A)B)(C)q
bool tryOp1(string& s, int pos, string& err) {
    // Pattern: (((A)B)C)
    // At pos, we should have '('
    if (pos < 0 || pos >= (int)s.length() || s[pos] != '(') {
        err = "Op 1: Invalid position";
        return false;
    }
    
    int m1 = findMatch(s, pos);  // Outer (...)
    if (m1 < 0 || pos + 1 >= (int)s.length() || s[pos+1] != '(') {
        err = "Op 1: Pattern mismatch";
        return false;
    }
    
    int m2 = findMatch(s, pos+1);  // ((A)B)
    if (m2 < 0 || m2 > m1 - 1 || pos + 2 >= (int)s.length() || s[pos+2] != '(') {
        err = "Op 1: Pattern mismatch";
        return false;
    }
    
    int m3 = findMatch(s, pos+2);  // (A)
    if (m3 < 0 || m3 > m2 - 1) {
        err = "Op 1: Pattern mismatch";
        return false;
    }
    
    // Extract A, B, C (can be empty)
    string A = extract(s, pos+3, m3-1);
    string B = extract(s, m3+1, m2-1);
    string C = extract(s, m2+1, m1-1);
    
    // Build result: ((A)B)(C)
    string replacement = "((" + A + ")" + B + ")(" + C + ")";
    s = s.substr(0, pos) + replacement + s.substr(m1+1);
    return true;
}

// Try to apply operation 2: p((A)(B)C)q -> p((A)B)(C)q
bool tryOp2(string& s, int pos, string& err) {
    if (pos < 0 || pos >= (int)s.length() || s[pos] != '(') {
        err = "Op 2: Invalid position";
        return false;
    }
    
    int m1 = findMatch(s, pos);
    if (m1 < 0 || pos + 1 >= (int)s.length() || s[pos+1] != '(') {
        err = "Op 2: Pattern mismatch";
        return false;
    }
    
    int m2 = findMatch(s, pos+1);  // (A)
    if (m2 < 0 || m2 >= m1 || m2 + 1 >= (int)s.length() || s[m2+1] != '(') {
        err = "Op 2: Pattern mismatch";
        return false;
    }
    
    int m3 = findMatch(s, m2+1);  // (B)
    if (m3 < 0 || m3 > m1 - 1) {
        err = "Op 2: Pattern mismatch";
        return false;
    }
    
    string A = extract(s, pos+2, m2-1);
    string B = extract(s, m2+2, m3-1);
    string C = extract(s, m3+1, m1-1);
    
    string replacement = "((" + A + ")" + B + ")(" + C + ")";
    s = s.substr(0, pos) + replacement + s.substr(m1+1);
    return true;
}

// Try to apply operation 3: p(A)((B)C)q -> p((A)B)(C)q
bool tryOp3(string& s, int pos, string& err) {
    if (pos < 0 || pos >= (int)s.length() || s[pos] != '(') {
        err = "Op 3: Invalid position";
        return false;
    }
    
    int m1 = findMatch(s, pos);  // (A)
    if (m1 < 0 || m1 + 1 >= (int)s.length() || s[m1+1] != '(') {
        err = "Op 3: Pattern mismatch";
        return false;
    }
    
    int m2 = findMatch(s, m1+1);  // ((B)C)
    if (m2 < 0 || m1 + 2 >= (int)s.length() || s[m1+2] != '(') {
        err = "Op 3: Pattern mismatch";
        return false;
    }
    
    int m3 = findMatch(s, m1+2);  // (B)
    if (m3 < 0 || m3 > m2 - 1) {
        err = "Op 3: Pattern mismatch";
        return false;
    }
    
    string A = extract(s, pos+1, m1-1);
    string B = extract(s, m1+3, m3-1);
    string C = extract(s, m3+1, m2-1);
    
    string replacement = "((" + A + ")" + B + ")(" + C + ")";
    s = s.substr(0, pos) + replacement + s.substr(m2+1);
    return true;
}

// Try to apply operation 4: p(A)(B)(C)q -> p((A)B)(C)q
bool tryOp4(string& s, int pos, string& err) {
    if (pos < 0 || pos >= (int)s.length() || s[pos] != '(') {
        err = "Op 4: Invalid position";
        return false;
    }
    
    int m1 = findMatch(s, pos);  // (A)
    if (m1 < 0 || m1 + 1 >= (int)s.length() || s[m1+1] != '(') {
        err = "Op 4: Pattern mismatch - no (B) after (A)";
        return false;
    }
    
    int m2 = findMatch(s, m1+1);  // (B)
    if (m2 < 0 || m2 + 1 >= (int)s.length() || s[m2+1] != '(') {
        err = "Op 4: Pattern mismatch - no (C) after (B)";
        return false;
    }
    
    int m3 = findMatch(s, m2+1);  // (C)
    if (m3 < 0) {
        err = "Op 4: Pattern mismatch - invalid (C)";
        return false;
    }
    
    string A = extract(s, pos+1, m1-1);
    string B = extract(s, m1+2, m2-1);
    string C = extract(s, m2+2, m3-1);
    
    string replacement = "((" + A + ")" + B + ")(" + C + ")";
    s = s.substr(0, pos) + replacement + s.substr(m3+1);
    return true;
}

bool applyOperations(const string& s1, const string& s2, 
                     const vector<pair<int, int>>& ops, 
                     int& op5_count, int& op6_count, string& errorMsg) {
    string current = s1;
    
    for (size_t i = 0; i < ops.size(); i++) {
        int opType = ops[i].first;
        int pos = ops[i].second;
        
        if (opType == 5) {
            op5_count++;
            if (pos < 0 || pos > (int)current.length()) {
                errorMsg = "Op 5: Invalid position " + to_string(pos);
                return false;
            }
            current = current.substr(0, pos) + "()" + current.substr(pos);
            
        } else if (opType == 6) {
            op6_count++;
            if (pos < 0 || pos + 1 >= (int)current.length()) {
                errorMsg = "Op 6: Invalid position " + to_string(pos);
                return false;
            }
            if (current[pos] != '(' || current[pos + 1] != ')') {
                errorMsg = "Op 6: No '()' at position " + to_string(pos);
                return false;
            }
            current = current.substr(0, pos) + current.substr(pos + 2);
            
        } else if (opType >= 1 && opType <= 4) {
            bool success = false;
            if (opType == 1) success = tryOp1(current, pos, errorMsg);
            else if (opType == 2) success = tryOp2(current, pos, errorMsg);
            else if (opType == 3) success = tryOp3(current, pos, errorMsg);
            else if (opType == 4) success = tryOp4(current, pos, errorMsg);
            
            if (!success) {
                errorMsg = "Step " + to_string(i+1) + ": " + errorMsg;
                return false;
            }
        } else {
            errorMsg = "Invalid operation type: " + to_string(opType);
            return false;
        }
    }
    
    if (current != s2) {
        errorMsg = "Final mismatch. Expected: " + s2 + ", Got: " + current;
        return false;
    }
    
    return true;
}

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    
    n = inf.readInt();
    string s1 = inf.readToken();
    string s2 = inf.readToken();
    
    if (!isValid(s1) || !isValid(s2)) {
        quitf(_fail, "Invalid input sequences");
    }
    
    int Q = ouf.readInt();
    if (Q < 0 || Q > 3 * n) {
        quitf(_wa, "Invalid Q: %d (must be 0 to %d)", Q, 3 * n);
    }
    
    vector<pair<int, int>> operations;
    for (int i = 0; i < Q; i++) {
        int opType = ouf.readInt();
        int pos = ouf.readInt();
        
        if (opType < 1 || opType > 6) {
            quitf(_wa, "Invalid operation type: %d", opType);
        }
        
        operations.push_back({opType, pos});
    }
    
    int op5_count = 0, op6_count = 0;
    string errorMsg;
    bool success = applyOperations(s1, s2, operations, op5_count, op6_count, errorMsg);
    
    if (op5_count > 2) {
        quitf(_wa, "Too many Op 5: %d (max: 2)", op5_count);
    }
    if (op6_count > 2) {
        quitf(_wa, "Too many Op 6: %d (max: 2)", op6_count);
    }
    
    if (!success) {
        quitf(_wa, "%s", errorMsg.c_str());
    }
    
    // Calculate score
    double threshold_full = 1.9 * n;  // Full score threshold
    double threshold_zero = 3.0 * n;  // Zero score threshold
    
    // Calculate raw score using linear interpolation
    // Raw score can be > 1.0 (when Q < threshold_full) or < 0.0 (when Q > threshold_zero)
    double raw_score = (threshold_zero - Q) / (threshold_zero - threshold_full);
    
    // Unbounded score: allow values > 1.0, but clip at 0.0
    double unbounded_score = max(0.0, raw_score);
    
    // Bounded score: clip to [0.0, 1.0] for submission score
    double score = max(0.0, min(1.0, raw_score));
    
    quitp(score, "Operations: %d, Ratio: %.4lf, RatioUnbounded: %.4lf", Q, score, unbounded_score);
    
    return 0;
}
