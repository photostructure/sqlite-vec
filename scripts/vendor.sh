#!/usr/bin/env bash
set -euo pipefail

# SQLite version and expected SHA-256 checksum
SQLITE_VERSION="3510100"
SQLITE_YEAR="2025"
SQLITE_ZIP="sqlite-amalgamation-${SQLITE_VERSION}.zip"
SQLITE_URL="https://www.sqlite.org/${SQLITE_YEAR}/${SQLITE_ZIP}"
EXPECTED_SHA256="84a85d6a1b920234349f01720912c12391a4f0cb5cb998087e641dee3ef8ef2e"

# Compute SHA-256 (works on both Linux and macOS)
compute_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "Error: No SHA-256 tool available (need sha256sum or shasum)" >&2
        exit 1
    fi
}

echo "Downloading SQLite amalgamation ${SQLITE_VERSION}..."
curl -fSL -o "${SQLITE_ZIP}" "${SQLITE_URL}"

echo "Verifying SHA-256 checksum..."
ACTUAL_SHA256=$(compute_sha256 "${SQLITE_ZIP}")

if [ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]; then
    echo "Error: SHA-256 checksum mismatch!" >&2
    echo "  Expected: ${EXPECTED_SHA256}" >&2
    echo "  Got:      ${ACTUAL_SHA256}" >&2
    rm -f "${SQLITE_ZIP}"
    exit 1
fi
echo "Checksum verified."

echo "Extracting..."
mkdir -p vendor
unzip -q "${SQLITE_ZIP}"
mv "sqlite-amalgamation-${SQLITE_VERSION}"/* vendor/
rmdir "sqlite-amalgamation-${SQLITE_VERSION}"
rm "${SQLITE_ZIP}"

echo "Done. SQLite ${SQLITE_VERSION} vendored to vendor/"
