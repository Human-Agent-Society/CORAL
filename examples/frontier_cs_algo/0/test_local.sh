#!/bin/bash
# Quick local test: compile solution + judge, run on a few test cases, print scores.
# Usage: bash test_local.sh [num_cases]  (default: 5)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL="$DIR/eval"
SEED="$DIR/seed"
TESTDATA="$EVAL/testdata"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

NUM_CASES=${1:-5}

echo "=== Compiling solution.cpp ==="
g++ -std=c++17 -O2 -o "$TMPDIR/solution" "$SEED/solution.cpp"
echo "OK"

echo "=== Compiling judge.cc ==="
g++ -std=c++17 -O2 -I"$EVAL" -o "$TMPDIR/judge" "$EVAL/judge.cc"
echo "OK"

# Collect test case numbers
CASES=($(ls "$TESTDATA"/*.in 2>/dev/null | sed 's/.*\///' | sed 's/\.in//' | sort -n | head -n "$NUM_CASES"))

if [ ${#CASES[@]} -eq 0 ]; then
    echo "No test cases found in $TESTDATA"
    exit 1
fi

echo "=== Running ${#CASES[@]} test cases ==="
TOTAL_SCORE=0
PASSED=0

for CASE in "${CASES[@]}"; do
    INPUT="$TESTDATA/${CASE}.in"
    ANSWER="$TESTDATA/${CASE}.ans"
    OUTPUT="$TMPDIR/out_${CASE}.txt"

    # Run solution with 5s timeout
    if timeout 5 "$TMPDIR/solution" < "$INPUT" > "$OUTPUT" 2>/dev/null; then
        # Run judge: judge <input> <answer> <output>
        RESULT=$("$TMPDIR/judge" "$INPUT" "$OUTPUT" "$ANSWER" 2>&1 || true)
        # Extract score from judge output
        if echo "$RESULT" | grep -q "Ratio:"; then
            RATIO=$(echo "$RESULT" | grep -oP 'Ratio: \K[0-9.]+')
            SCORE=$(python3 -c "print(round(float('$RATIO') * 1e5, 2))")
            echo "  Case $CASE: score=$SCORE  ($RESULT)"
            TOTAL_SCORE=$(python3 -c "print($TOTAL_SCORE + $SCORE)")
            PASSED=$((PASSED + 1))
        else
            echo "  Case $CASE: FAILED - $RESULT"
        fi
    else
        echo "  Case $CASE: TLE or RE"
    fi
done

if [ $PASSED -gt 0 ]; then
    AVG=$(python3 -c "print(round($TOTAL_SCORE / $PASSED, 2))")
    echo ""
    echo "=== Results: $PASSED/${#CASES[@]} passed, avg score per case: $AVG ==="
    echo "=== Estimated total (if all 70 similar): $(python3 -c "print(round($AVG * 70 / 70, 2))") ==="
fi
