#!/usr/bin/env bash
#
# Prepare a release branch with version bumps.
#
# Usage: ./scripts/prepare-release.sh <patch|minor|major>
#        DRY_RUN=1 ./scripts/prepare-release.sh patch  # test without commit/push
#
# This script:
#   1. Reads current version from VERSION file
#   2. Calculates new version using semver bump
#   3. Creates a release branch
#   4. Updates VERSION, sqlite-vec.h, and package.json
#   5. Commits and pushes the release branch
#
# Outputs (for GitHub Actions):
#   - Writes branch=<name> and version=<version> to $GITHUB_OUTPUT if set
#
# Why this exists (replacing scripts/publish-release.sh):
#
#   The original publish-release.sh pushed version bumps to main BEFORE CI
#   builds completed. If builds failed, main was left in an inconsistent state
#   with a version tag pointing to broken artifacts.
#
#   This script is part of a safer release flow:
#
#   1. RELEASE BRANCH ISOLATION: Version bumps happen on a release/vX.Y.Z
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

BUMP_TYPE="${1:-patch}"

if [[ ! "$BUMP_TYPE" =~ ^(patch|minor|major)$ ]]; then
  echo "Usage: $0 <patch|minor|major>" >&2
  exit 1
fi

# Get current version from VERSION file (source of truth)
CURRENT=$(cat VERSION | tr -d '[:space:]')
echo "Current version: $CURRENT"

# Calculate new version (strip prerelease suffix, then bump)
BASE_VERSION=$(echo "$CURRENT" | sed 's/-.*//')
NEW_VERSION=$(npx -y semver -i "$BUMP_TYPE" "$BASE_VERSION")
echo "New version: $NEW_VERSION"

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
