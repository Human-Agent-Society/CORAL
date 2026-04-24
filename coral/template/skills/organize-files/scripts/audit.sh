#!/usr/bin/env bash
# audit.sh — Quick read-only audit of a notes directory.
# Usage: bash audit.sh [NOTES_DIR]
# Defaults to .coral/public/notes if no argument given.
# This script NEVER modifies any files.

set -euo pipefail

NOTES_DIR="${1:-.coral/public/notes}"

if [ ! -d "$NOTES_DIR" ]; then
    echo "Directory not found: $NOTES_DIR"
    exit 1
fi

echo "=== Notes Audit ==="
echo "Directory: $NOTES_DIR"
echo ""

# --- File count ---
total=$(find "$NOTES_DIR" -name '*.md' -type f | wc -l | tr -d ' ')
top_level=$(find "$NOTES_DIR" -maxdepth 1 -name '*.md' -type f | wc -l | tr -d ' ')
in_subdirs=$((total - top_level))
echo "File count: $total total ($top_level top-level, $in_subdirs in subdirectories)"
echo ""

# --- Directory tree (compact) ---
echo "Directory structure:"
if command -v tree &>/dev/null; then
    tree "$NOTES_DIR" --dirsfirst -I '__pycache__' --noreport 2>/dev/null || find "$NOTES_DIR" -type d | sort
else
    find "$NOTES_DIR" -type d | sort | while read -r dir; do
        depth=$(echo "$dir" | sed "s|$NOTES_DIR||" | tr -cd '/' | wc -c | tr -d ' ')
        indent=$(printf '%*s' "$((depth * 2))" '')
        echo "${indent}$(basename "$dir")/"
    done
fi
echo ""

# --- Naming issues ---
echo "Naming issues:"
issues=0

# Files with spaces
while IFS= read -r f; do
    if [ -n "$f" ]; then
        echo "  [space] $(basename "$f")"
        issues=$((issues + 1))
    fi
done < <(find "$NOTES_DIR" -name '* *' -name '*.md' -type f 2>/dev/null)

# Files with uppercase
while IFS= read -r f; do
    if [ -n "$f" ]; then
        base=$(basename "$f")
        if echo "$base" | grep -q '[A-Z]' && [ "$base" != "SKILL.md" ] && ! echo "$base" | grep -q '^_'; then
            echo "  [uppercase] $base"
            issues=$((issues + 1))
        fi
    fi
done < <(find "$NOTES_DIR" -name '*.md' -type f 2>/dev/null)

# Files missing frontmatter
while IFS= read -r f; do
    if [ -n "$f" ]; then
        base=$(basename "$f")
        # Skip underscore-prefixed meta files
        if echo "$base" | grep -q '^_'; then
            continue
        fi
        first_line=$(head -n 1 "$f" 2>/dev/null || true)
        if [ "$first_line" != "---" ]; then
            echo "  [no frontmatter] $base"
            issues=$((issues + 1))
        fi
    fi
done < <(find "$NOTES_DIR" -name '*.md' -type f 2>/dev/null)

if [ "$issues" -eq 0 ]; then
    echo "  None found."
fi
echo ""

# --- Recent activity (last 60 minutes) ---
echo "Recent activity (last 60 min):"
recent=0

# Detect stat flavor (macOS vs Linux)
if stat -f '%m' /dev/null &>/dev/null 2>&1; then
    # macOS
    now=$(date +%s)
    cutoff=$((now - 3600))
    while IFS= read -r f; do
        if [ -n "$f" ]; then
            mtime=$(stat -f '%m' "$f" 2>/dev/null || echo 0)
            if [ "$mtime" -gt "$cutoff" ]; then
                echo "  $(basename "$f") (modified $(( (now - mtime) / 60 ))m ago)"
                recent=$((recent + 1))
            fi
        fi
    done < <(find "$NOTES_DIR" -name '*.md' -type f 2>/dev/null)
else
    # Linux
    while IFS= read -r f; do
        if [ -n "$f" ]; then
            echo "  $(basename "$f")"
            recent=$((recent + 1))
        fi
    done < <(find "$NOTES_DIR" -name '*.md' -type f -mmin -60 2>/dev/null)
fi

if [ "$recent" -eq 0 ]; then
    echo "  No files modified in the last 60 minutes."
fi
echo ""

# --- Creator distribution ---
echo "Creator distribution:"
creators=$(grep -rh '^creator:' "$NOTES_DIR"/*.md "$NOTES_DIR"/**/*.md 2>/dev/null | sed 's/^creator:[[:space:]]*//' | sort | uniq -c | sort -rn)
if [ -n "$creators" ]; then
    echo "$creators" | while read -r count name; do
        echo "  $name: $count notes"
    done
else
    echo "  No creator metadata found."
fi
echo ""

echo "=== End Audit ==="
