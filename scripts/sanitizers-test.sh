#!/bin/bash
#
# Sanitizer test runner for sqlite-vec
# Supports AddressSanitizer (ASan), UndefinedBehaviorSanitizer (UBSan), and ThreadSanitizer (TSan)
#
# Usage: ./scripts/sanitizers-test.sh [asan|ubsan|tsan]
# Or:    make test-asan / make test-ubsan / make test-tsan

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Determine which sanitizer to run
SANITIZER="${1:-asan}"

case "$SANITIZER" in
  asan)
    SANITIZER_NAME="AddressSanitizer + LeakSanitizer"
    SANITIZER_FLAGS="-fsanitize=address,leak"
    OUTPUT_FILE="$ROOT_DIR/asan-output.log"
    MEMORY_TEST="$ROOT_DIR/dist/memory-test-asan"
    ASAN_OPTIONS="detect_leaks=1:halt_on_error=1:print_stats=1:check_initialization_order=1"
    LSAN_OPTIONS="print_suppressions=0"
    ;;
  ubsan)
    SANITIZER_NAME="UndefinedBehaviorSanitizer"
    SANITIZER_FLAGS="-fsanitize=undefined"
    OUTPUT_FILE="$ROOT_DIR/ubsan-output.log"
    MEMORY_TEST="$ROOT_DIR/dist/memory-test-ubsan"
    UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
    ;;
  tsan)
    SANITIZER_NAME="ThreadSanitizer"
    SANITIZER_FLAGS="-fsanitize=thread"
    OUTPUT_FILE="$ROOT_DIR/tsan-output.log"
    MEMORY_TEST="$ROOT_DIR/dist/memory-test-tsan"
    TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1"
    ;;
  *)
    echo -e "${RED}Error: Unknown sanitizer '$SANITIZER'${NC}"
    echo "Usage: $0 [asan|ubsan|tsan]"
    exit 1
    ;;
esac

# Only run on Linux (macOS has SIP issues with some sanitizers)
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    if [[ "$SANITIZER" == "tsan" ]]; then
        echo -e "${YELLOW}ThreadSanitizer requires Linux. Skipping on $OSTYPE.${NC}"
        exit 0
    fi
    # ASan and UBSan can work on macOS
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo -e "${YELLOW}Sanitizer tests currently only supported on Linux and macOS.${NC}"
        exit 0
    fi
fi

# Check for clang or gcc
CC="${CC:-}"
if [[ -z "$CC" ]]; then
    if command -v clang &>/dev/null; then
        CC=clang
    elif command -v gcc &>/dev/null; then
        CC=gcc
    else
        echo -e "${RED}Error: Neither clang nor gcc found. Install one to run sanitizer tests.${NC}"
        exit 1
    fi
fi

echo -e "${BLUE}=== $SANITIZER_NAME Tests ===${NC}"
echo "Using compiler: $CC"

# Clean previous output
rm -f "$OUTPUT_FILE"

# Sanitizer compiler flags
SANITIZER_CFLAGS="$SANITIZER_FLAGS -fno-omit-frame-pointer -g -O1"
SANITIZER_LDFLAGS="$SANITIZER_FLAGS"

# Build the sanitizer-instrumented memory test
echo -e "\n${YELLOW}Building memory-test with $SANITIZER_NAME...${NC}"

$CC $SANITIZER_CFLAGS \
    -fvisibility=hidden \
    -I"$ROOT_DIR/vendor/" -I"$ROOT_DIR/" \
    -DSQLITE_CORE \
    -DSQLITE_VEC_STATIC \
    -DSQLITE_THREADSAFE=0 \
    "$ROOT_DIR/tests/memory-test.c" \
    "$ROOT_DIR/sqlite-vec.c" \
    "$ROOT_DIR/vendor/sqlite3.c" \
    -o "$MEMORY_TEST" \
    $SANITIZER_LDFLAGS -ldl -lm

if [ ! -f "$MEMORY_TEST" ]; then
    echo -e "${RED}Error: Sanitizer build failed. Binary not found at $MEMORY_TEST${NC}"
    exit 1
fi
echo -e "${GREEN}Sanitizer build complete${NC}"

# Set sanitizer options
export ASAN_OPTIONS="${ASAN_OPTIONS:-}"
export LSAN_OPTIONS="${LSAN_OPTIONS:-}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-}"
export TSAN_OPTIONS="${TSAN_OPTIONS:-}"

# Run the sanitizer-instrumented memory test
echo -e "\n${YELLOW}Running memory tests with $SANITIZER_NAME...${NC}"

set +e
"$MEMORY_TEST" 2>&1 | tee "$OUTPUT_FILE"
TEST_EXIT=${PIPESTATUS[0]}
set -e

echo ""

# Analyze output for sanitizer errors
echo -e "${BLUE}=== Analyzing $SANITIZER_NAME output ===${NC}"

RESULT=0

# Check for AddressSanitizer errors
if [[ "$SANITIZER" == "asan" ]] && grep -q "ERROR: AddressSanitizer" "$OUTPUT_FILE"; then
    echo -e "${RED}FAIL: AddressSanitizer found errors:${NC}"
    grep -B 2 -A 20 "ERROR: AddressSanitizer" "$OUTPUT_FILE" | head -50 || true
    RESULT=1
fi

# Check for LeakSanitizer errors
if [[ "$SANITIZER" == "asan" ]] && grep -q "ERROR: LeakSanitizer" "$OUTPUT_FILE"; then
    echo -e "${RED}FAIL: LeakSanitizer found memory leaks:${NC}"
    grep -B 2 -A 30 "ERROR: LeakSanitizer" "$OUTPUT_FILE" | head -60 || true
    RESULT=1
fi

# Check for UndefinedBehaviorSanitizer errors
if [[ "$SANITIZER" == "ubsan" ]] && grep -q "runtime error:" "$OUTPUT_FILE"; then
    echo -e "${RED}FAIL: UndefinedBehaviorSanitizer found issues:${NC}"
    grep -B 2 -A 5 "runtime error:" "$OUTPUT_FILE" | head -30 || true
    RESULT=1
fi

# Check for ThreadSanitizer errors
if [[ "$SANITIZER" == "tsan" ]] && grep -q "WARNING: ThreadSanitizer" "$OUTPUT_FILE"; then
    echo -e "${RED}FAIL: ThreadSanitizer found data races:${NC}"
    grep -B 2 -A 20 "WARNING: ThreadSanitizer" "$OUTPUT_FILE" | head -50 || true
    RESULT=1
fi

# Check test exit code
if [[ "$TEST_EXIT" -ne 0 && "$RESULT" -eq 0 ]]; then
    echo -e "${RED}FAIL: Tests failed with exit code $TEST_EXIT${NC}"
    RESULT=1
fi

if [[ "$RESULT" -eq 0 ]]; then
    echo -e "\n${GREEN}PASS: No errors detected by $SANITIZER_NAME${NC}"
    rm -f "$OUTPUT_FILE"
else
    echo -e "\n${RED}Issues detected! See $OUTPUT_FILE for full details.${NC}"
fi

# Clean up sanitizer build artifacts
echo -e "\n${YELLOW}Cleaning up sanitizer build...${NC}"
rm -f "$MEMORY_TEST"
echo -e "${GREEN}Cleanup complete${NC}"

exit $RESULT
