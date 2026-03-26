#!/bin/bash
# Master script - shows assignment and how to run each group
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cat << 'BANNER'
================================================================
  Frontier-CS Competition Runner
  6 groups x 15 problems = 90 problems total
  3 groups algo + 3 groups research
  4 groups Claude Code Opus + 2 groups Codex GPT-5.4
  1 agent per problem, verbose, no internet, 1.5 hours each
================================================================
BANNER

echo ""
echo "Group assignments:"
echo "  Group 1 (Person 1): algo  0-15   | Claude Code Opus  | bash group1_algo_opus.sh"
echo "  Group 2 (Person 2): algo 16-41   | Claude Code Opus  | bash group2_algo_opus.sh"
echo "  Group 3 (Person 3): algo 42-60   | Codex GPT-5.4     | bash group3_algo_codex.sh"
echo "  Group 4 (Person 4): research GPU | Claude Code Opus  | bash group4_research_opus.sh"
echo "  Group 5 (Person 5): research ML  | Claude Code Opus  | bash group5_research_opus.sh"
echo "  Group 6 (Person 6): research mix | Codex GPT-5.4     | bash group6_research_codex.sh"
echo ""
echo "Each person runs their script on their machine."
echo "CSVs are written to: $SCRIPT_DIR/results/"
echo ""
echo "To run a specific group:  cd $SCRIPT_DIR && bash group<N>_*.sh"
echo "To check progress:        cat $SCRIPT_DIR/results/group<N>_*.csv"
echo ""

# Optionally run a specific group
if [ "${1:-}" != "" ]; then
    script="$SCRIPT_DIR/$1"
    if [ -f "$script" ]; then
        echo "Running: $1"
        bash "$script"
    else
        echo "Script not found: $1"
        echo "Available scripts:"
        ls "$SCRIPT_DIR"/group*.sh
        exit 1
    fi
fi
