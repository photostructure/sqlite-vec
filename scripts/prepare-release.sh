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
#   3. Refuses to continue unless CHANGELOG.md has notes under
#      `## [VERSION] - YYYY-MM-DD`
#   4. Creates a release branch
#   5. Syncs VERSION to sqlite-vec.h and package.json
#   6. Commits and pushes the release branch
#
# Outputs (for GitHub Actions):
#   - Writes branch=<name>, version=<version>, and commit=<sha> to
#     $GITHUB_OUTPUT if set
#
# Developer workflow:
#   1. Manually bump VERSION file (e.g., 0.4.0 → 0.4.1)
#   2. Rename `## [Unreleased]` in CHANGELOG.md to `## [0.4.1] - YYYY-MM-DD`
#   3. Commit: git commit -am "release: prepare v0.4.1"
#   4. Wait for Test and Memory Tests to pass on that commit
#   5. Trigger release.yaml workflow
#   6. The workflows build, tag, stage, and wait for maintainer 2FA approval
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
#   3. OIDC AUTHENTICATION: The tag-bound publish workflow uses OpenID Connect
#      with GitHub's identity provider, with no long-lived npm token.
#
#   4. PROVENANCE ATTESTATION: The publisher starts at the signed release tag,
#      so npm provenance identifies the same commit that built the package.
#
#   5. HUMAN APPROVAL: CI stages the package; a maintainer reviews and approves
#      it with 2FA before npm makes it public.
#
# See .github/workflows/release.yaml and .github/workflows/publish.yaml.
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

# The first prerelease identifier becomes the npm dist-tag. Keep this set
# explicit so every accepted VERSION is publishable before an immutable tag is
# created; npm rejects tags that parse as SemVer ranges (for example, v1).
if [[ "$VERSION" == *-* ]]; then
  PRERELEASE="${VERSION#*-}"
  DIST_TAG="${PRERELEASE%%.*}"
  case "$DIST_TAG" in
    alpha | beta | rc) ;;
    *)
      echo "ERROR: Prerelease must start with alpha, beta, or rc: '$VERSION'" >&2
      exit 1
      ;;
  esac
fi

# publish.yaml copies this section into the GitHub release notes after npm
# publishes the package. Check it here, before anything is tagged.
NOTES="$(awk -v heading="## [$VERSION] - " \
  'index($0, heading) == 1 { found = 1; next } found && /^## / { exit } found' \
  CHANGELOG.md)"
if ! grep -q '[^[:space:]]' <<< "$NOTES"; then
  echo "ERROR: CHANGELOG.md has no notes under '## [$VERSION] - YYYY-MM-DD'." >&2
  echo "Rename '## [Unreleased]' to '## [$VERSION] - $(date -u +%F)', keep its" >&2
  echo "notes, commit to main, wait for Test and Memory Tests to pass on that" >&2
  echo "commit, and start the release again." >&2
  exit 1
fi

# Create release branch
BRANCH="release/v${VERSION}"
git checkout -b "$BRANCH"

# Regenerate sqlite-vec.h from template (uses VERSION file).
#
# The rm is required, not tidiness: a fresh CI checkout stamps every file with
# the same mtime, and make treats a target that is merely not-older than its
# prerequisites as up to date. So plain `make sqlite-vec.h` prints "up to date"
# and silently keeps the committed header, which is how the version stayed at
# v0.4.0 in every binary from v0.4.1 through v1.2.0.
rm -f sqlite-vec.h
make sqlite-vec.h

# Fail loudly if the header did not pick up VERSION, rather than shipping
# binaries whose vec_version() disagrees with the package version.
if ! grep -q "define SQLITE_VEC_VERSION \"v${VERSION}\"" sqlite-vec.h; then
  echo "ERROR: sqlite-vec.h was not regenerated for v${VERSION}:" >&2
  grep "define SQLITE_VEC_VERSION " sqlite-vec.h >&2
  exit 1
fi

# Sync VERSION to package.json and package-lock.json
npm version "$VERSION" --no-git-tag-version --allow-same-version
npm install --package-lock-only --ignore-scripts

# Commit version sync (VERSION should already be committed on main)
git add sqlite-vec.h package.json package-lock.json

if [[ -n "${DRY_RUN:-}" ]]; then
  echo ""
  echo "=== DRY RUN MODE ==="
  echo "Would commit and push branch '$BRANCH' with version $VERSION"
  echo ""
  echo "Files to be committed:"
  git diff --cached --name-only
  echo ""
  echo "To clean up:"
  echo "  git reset HEAD && git checkout -- . && git checkout main && git branch -D $BRANCH"
  exit 0
fi

# Only commit if there are changes (VERSION might already be synced)
if ! git diff --cached --quiet; then
  git commit -S -m "release: sync package.json to v${VERSION}"
  echo "Committed package.json sync for v${VERSION}"
else
  echo "No changes to commit (package.json already synced)"
fi

git push origin "$BRANCH"

RELEASE_COMMIT="$(git rev-parse HEAD)"

# Output for GitHub Actions
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "branch=$BRANCH"
    echo "version=$VERSION"
    echo "commit=$RELEASE_COMMIT"
  } >> "$GITHUB_OUTPUT"
fi

echo "Release branch '$BRANCH' created and pushed."
echo "Version: $VERSION"
