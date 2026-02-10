#!/usr/bin/env bash
#
# Prepare a release branch using VERSION file as source of truth.
#
# Usage: ./scripts/prepare-release.sh
#        DRY_RUN=1 ./scripts/prepare-release.sh  # test without commit/push
#
# This script:
#   1. Reads version from VERSION file (must be bumped manually beforehand)
#   2. Validates VERSION looks like valid semver
#   3. Creates a release branch
#   4. Syncs VERSION to sqlite-vec.h and package.json
#   5. Commits and pushes the release branch
#
# Outputs (for GitHub Actions):
#   - Writes branch=<name> and version=<version> to $GITHUB_OUTPUT if set
#
# Developer workflow:
#   1. Manually bump VERSION file (e.g., 0.4.0 → 0.4.1)
#   2. Update CHANGELOG-mceachen.md with changes
#   3. Commit: git commit -am "release: prepare v0.4.1"
#   4. Trigger npm-release.yaml workflow
#   5. Workflow runs this script, builds, publishes, merges to main
#
# Why VERSION is source of truth:
#
#   - Clear and transparent: "The version is whatever VERSION says"
#   - Prepare releases: Update CHANGELOG for new version before workflow runs
#   - Git history: Version bumps are explicit, visible commits
#   - Standard practice: Similar to Go modules, Rust crates, etc.
#
# Why this release flow exists:
#
#   1. RELEASE BRANCH ISOLATION: VERSION sync happens on a release/vX.Y.Z
#      branch. Main is untouched until everything succeeds.
#
#   2. CORRECT VERSION IN BINARIES: All platform builds check out the release
#      branch, so the version in sqlite-vec.h is baked into every binary.
#
#   3. OIDC AUTHENTICATION: npm publishing uses OpenID Connect with GitHub's
#      identity provider - no long-lived npm tokens to rotate or leak.
#
#   4. PROVENANCE ATTESTATION: npm publish --provenance creates a signed,
#      verifiable link between the published package and this GitHub repo,
#      commit, and workflow run. Users can audit exactly what built their
#      package.
#
#   5. ATOMIC SUCCESS: Only after npm publish succeeds does the workflow merge
#      to main, create the signed tag, and create the GitHub release. If
#      anything fails, main is unchanged and the release branch can be deleted.
#
# See .github/workflows/npm-release.yaml for the full workflow.
#
set -euo pipefail

# Get version from VERSION file (source of truth)
VERSION=$(cat VERSION | tr -d '[:space:]')
echo "Releasing version: $VERSION"

# Validate VERSION looks like semver (basic check)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  echo "ERROR: VERSION file contains invalid semver: '$VERSION'" >&2
  echo "Expected format: X.Y.Z or X.Y.Z-prerelease" >&2
  exit 1
fi

# Create release branch
BRANCH="release/v${NEW_VERSION}"
git checkout -b "$BRANCH"

# Update VERSION file
echo "$NEW_VERSION" > VERSION

# Regenerate sqlite-vec.h from template
make sqlite-vec.h

# Update package.json and package-lock.json
npm version "$NEW_VERSION" --no-git-tag-version
npm install --package-lock-only

# Commit all version changes
git add VERSION sqlite-vec.h package.json package-lock.json

if [[ -n "${DRY_RUN:-}" ]]; then
  echo ""
  echo "=== DRY RUN MODE ==="
  echo "Would commit and push branch '$BRANCH' with version $NEW_VERSION"
  echo ""
  echo "Files staged:"
  git diff --cached --name-only
  echo ""
  echo "To clean up:"
  echo "  git reset HEAD && git checkout -- . && git checkout main && git branch -D $BRANCH"
  exit 0
fi

git commit -S -m "release: v${NEW_VERSION}"
git push origin "$BRANCH"

# Output for GitHub Actions
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "branch=$BRANCH" >> "$GITHUB_OUTPUT"
  echo "version=$NEW_VERSION" >> "$GITHUB_OUTPUT"
fi

echo "Release branch '$BRANCH' created and pushed."
echo "Version: $NEW_VERSION"
