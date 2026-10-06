#!/bin/sh

# Install an npm tarball of @photostructure/sqlite-vec into an empty project
# and run tests/test-npm-package.mjs against the installed copy. POSIX sh so
# release.yaml can run it unchanged on Alpine, macOS, and Git Bash on Windows.
#
# Usage: SQLITE_VEC_EXPECTED_BINARY=dist/linux-x64/vec0.so \
#          tests/test-npm-package.sh path/to/package.tgz

set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <package.tgz>" >&2
  exit 1
fi

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
CONSUMER="$(mktemp -d)"
trap 'rm -rf "$CONSUMER"' EXIT

cp "$1" "$CONSUMER/package.tgz"
cp "$TESTS_DIR/test-npm-package.mjs" "$CONSUMER/"
echo '{ "private": true }' > "$CONSUMER/package.json"

cd "$CONSUMER"
npm install --ignore-scripts --no-audit --no-fund ./package.tgz
node --test test-npm-package.mjs
