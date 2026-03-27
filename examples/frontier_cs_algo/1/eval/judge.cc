#include "testlib.h"
#include <vector>
#include <string>
#include <map>
#include <algorithm>

using namespace std;

// --- Robust JSON Parser ---
void skipWhitespace(InStream& stream) { while (!stream.eof() && isspace(stream.curChar())) stream.readChar(); }
void expectChar(InStream& stream, char expected) { skipWhitespace(stream); char actual = stream.readChar(); if (actual != expected) quitf(_fail, "Expected char '%c', found '%c'", expected, actual); }
string readQuotedString(InStream& stream) { skipWhitespace(stream); expectChar(stream, '"'); string s; char c; while ((c = stream.readChar()) != '"') s += c; return s; }
long long readLongAndComma(InStream& stream, bool must_have_comma) {
    skipWhitespace(stream); string token = stream.readToken();
    if (must_have_comma) {
        if (token.empty() || token.back() != ',') quitf(_fail, "Input format: expected comma after number, got '%s'", token.c_str());
        token.pop_back();
    }
    try { return stoll(token); } catch (...) { quitf(_fail, "Input format: cannot parse '%s'", token.c_str()); }
}

map<string, vector<long long>> read_input_json(InStream& stream) {
    map<string, vector<long long>> data;
    expectChar(stream, '{');
    for (int i = 0; i < 12; ++i) {
        if (i > 0) expectChar(stream, ',');
        string key = readQuotedString(stream);
        expectChar(stream, ':');
        expectChar(stream, '[');
        data[key] = {readLongAndComma(stream, true), readLongAndComma(stream, true), readLongAndComma(stream, true), readLongAndComma(stream, false)};
        expectChar(stream, ']');
    }
    expectChar(stream, '}');
    return data;
}

// THIS FUNCTION IS NOW ROBUST
map<string, long long> read_output_json(InStream& stream) {
    map<string, long long> data;
    expectChar(stream, '{');
    for (int i = 0; i < 12; ++i) {
        string key = readQuotedString(stream);
        expectChar(stream, ':');
        // Manually read the token to handle optional commas
        skipWhitespace(stream);
        string token = stream.readToken();
        if (!token.empty() && token.back() == ',') {
            token.pop_back();
        }
        try {
            data[key] = stoll(token);
        } catch (...) {
            quitf(_wa, "Could not parse participant output value '%s' for key '%s'", token.c_str(), key.c_str());
        }
    }
    expectChar(stream, '}');
    return data;
}

// --- Checker Main Logic ---
int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    auto items = read_input_json(inf);
    auto participant_counts = read_output_json(ouf);
    long long baseline_value = ans.readLong();
    long long best_value = ans.readLong();
    long long total_mass = 0, total_volume = 0, participant_value = 0;
    if (participant_counts.size() != 12) quitf(_wa, "Output must contain exactly 12 keys");
    for (auto const& [key, count] : participant_counts) {
        if (items.find(key) == items.end()) quitf(_wa, "Unknown key: %s", key.c_str());
        if (count < 0) quitf(_wa, "Negative items for %s", key.c_str());
        if (count > items[key][0]) quitf(_wa, "Too many items for %s", key.c_str());
        participant_value += count * items[key][1];
        total_mass += count * items[key][2];
        total_volume += count * items[key][3];
    }
    long long max_mass = 20000000, max_volume = 25000000;
    if (total_mass > max_mass) quitf(_wa, "Total mass exceeds limit");
    if (total_volume > max_volume) quitf(_wa, "Total volume exceeds limit");
    double score_ratio = 0, unbounded_ratio = 0;
    if (best_value <= baseline_value) {
        if (participant_value >= best_value) score_ratio = 1.0;
        else score_ratio = 0.0;
    }
    else {
        score_ratio = max(0.0, min(1.0, (double)(participant_value - baseline_value) / (best_value - baseline_value)));
        unbounded_ratio = (double)(participant_value - baseline_value) / (best_value - baseline_value);
    }
    bool correct = (score_ratio == 1.0);
    quitp(score_ratio, "Value: %lld. Ratio: %.4f, RatioUnbounded: %.4f", participant_value, score_ratio, unbounded_ratio);
}