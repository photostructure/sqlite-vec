#!/bin/bash
#
# clang-tidy static analysis for sqlite-vec
# Detects potential bugs, style issues, and code smells
#
# Usage: ./scripts/clang-tidy.sh
# Or:    make lint-clang-tidy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== clang-tidy Static Analysis ===${NC}"

# Check if clang-tidy is available
if ! command -v clang-tidy &>/dev/null; then
    echo -e "${YELLOW}Warning: clang-tidy not found.${NC}"
    echo "Install with:"
    echo "  Linux: sudo apt-get install clang-tidy"
    echo "  macOS: brew install llvm"
    exit 0
fi

echo "Using: $(clang-tidy --version | head -1)"

# Check if compile_commands.json exists
if [ ! -f "$ROOT_DIR/compile_commands.json" ]; then
    echo -e "${YELLOW}compile_commands.json not found. Generating with bear...${NC}"

    # Check if bear is available
    if ! command -v bear &>/dev/null; then
        echo -e "${YELLOW}Warning: bear not found. Install with:${NC}"
        echo "  Linux: sudo apt-get install bear"
        echo "  macOS: brew install bear"
        echo ""
        echo -e "${YELLOW}Running clang-tidy without compile_commands.json (less accurate)${NC}"
    else
        # Generate compile_commands.json
        echo "Generating compile_commands.json with bear..."
        cd "$ROOT_DIR"
        if bear -- make clean all >/dev/null 2>&1; then
            echo -e "${GREEN}Generated compile_commands.json${NC}"
        else
            echo -e "${YELLOW}Failed to generate compile_commands.json, continuing without it${NC}"
            rm -f "$ROOT_DIR/compile_commands.json"
        fi
    fi
fi

# Output file
OUTPUT_FILE="$ROOT_DIR/clang-tidy-output.txt"
rm -f "$OUTPUT_FILE"

# Run clang-tidy
set +e
if [ -f "$ROOT_DIR/compile_commands.json" ]; then
    clang-tidy \
        -p="$ROOT_DIR" \
        "$ROOT_DIR/sqlite-vec.c" \
        2>&1 | tee "$OUTPUT_FILE"
    TIDY_EXIT=${PIPESTATUS[0]}
else
    # Fallback: run without compile_commands.json
    clang-tidy \
        "$ROOT_DIR/sqlite-vec.c" \
        -- \
        -I"$ROOT_DIR/vendor/" \
        -DSQLITE_CORE \
        -DSQLITE_VEC_STATIC \
        2>&1 | tee "$OUTPUT_FILE"
    TIDY_EXIT=${PIPESTATUS[0]}
fi
set -e

echo ""

# Count warnings and errors
WARNING_COUNT=$(grep -c "warning:" "$OUTPUT_FILE" 2>/dev/null || echo "0")
ERROR_COUNT=$(grep -c "error:" "$OUTPUT_FILE" 2>/dev/null || echo "0")

echo -e "${BLUE}=== clang-tidy Summary ===${NC}"
echo "  Warnings: $WARNING_COUNT"
echo "  Errors:   $ERROR_COUNT"

if [[ "$WARNING_COUNT" -eq 0 && "$ERROR_COUNT" -eq 0 ]]; then
    echo -e "\n${GREEN}PASS: No issues found by clang-tidy${NC}"
    rm -f "$OUTPUT_FILE"
    exit 0
else
    echo -e "\n${YELLOW}Issues found. See $OUTPUT_FILE for details.${NC}"

    # Show top issues
    if [[ "$WARNING_COUNT" -gt 0 ]]; then
        echo -e "\n${YELLOW}Top warnings:${NC}"
        grep "warning:" "$OUTPUT_FILE" | head -10
    fi

    if [[ "$ERROR_COUNT" -gt 0 ]]; then
        echo -e "\n${RED}Errors:${NC}"
        grep "error:" "$OUTPUT_FILE" | head -10
    fi

    # Don't fail the build for clang-tidy warnings (informational only)
    exit 0
fi
