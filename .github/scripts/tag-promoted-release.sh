#!/usr/bin/env bash

set -euo pipefail

: "${SOURCE_REF:?SOURCE_REF must identify the promoted dev commit}"
: "${PROMOTED_REF:?PROMOTED_REF must identify the resulting main commit}"

BUMP="${BUMP:-patch}"
FORCE="${FORCE:-false}"

write_output() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
}

# The checkout action fetches full history, but explicit branch refs make
# workflow_dispatch inputs such as origin/dev deterministic as well.
git fetch --force --tags origin \
  '+refs/heads/main:refs/remotes/origin/main' \
  '+refs/heads/dev:refs/remotes/origin/dev'

source_sha=$(git rev-parse --verify "${SOURCE_REF}^{commit}")
promoted_sha=$(git rev-parse --verify "${PROMOTED_REF}^{commit}")

echo "Promoted dev commit: $source_sha"
echo "Resulting main commit: $promoted_sha"

if ! git merge-base --is-ancestor "$source_sha" "$promoted_sha"; then
  echo "::error::The selected dev commit is not an ancestor of the main promotion commit."
  exit 1
fi

if ! git merge-base --is-ancestor "$promoted_sha" origin/main; then
  echo "::error::The promotion commit is not present on origin/main."
  exit 1
fi

# A promotion merge should add history metadata only. Tagging the dev parent is
# safe only when it contains exactly the source tree that landed on main.
if ! git diff --quiet "${source_sha}^{tree}" "${promoted_sha}^{tree}"; then
  echo "::error::The promoted dev tree differs from the resulting main tree."
  git diff --stat "${source_sha}^{tree}" "${promoted_sha}^{tree}"
  exit 1
fi

existing=$(git tag --points-at "$source_sha" --list 'v[0-9]*' --sort=-v:refname | head -n1)
if [[ -n "$existing" && "$FORCE" != "true" ]]; then
  echo "Promoted commit is already tagged as $existing; reusing it."
  write_output tagged true
  write_output version "$existing"
  write_output source_sha "$source_sha"
  exit 0
fi

latest=$(git tag --list 'v[0-9]*' --sort=-v:refname | head -n1)
if [[ -z "$latest" ]]; then
  latest="v0.0.0"
  base_range=""
  echo "No existing release tag found; starting from $latest."
else
  base_range="${latest}..${source_sha}"
  echo "Latest release tag: $latest"

  # During migration, the latest legacy tag may point at a main-only merge
  # commit. It is still safe to advance when that tag and the dev source are
  # both ancestors of the verified promotion commit. The new tag repairs the
  # shared ancestry for all subsequent dev commits.
  if ! git merge-base --is-ancestor "$latest" "$source_sha"; then
    if git merge-base --is-ancestor "$latest" "$promoted_sha"; then
      echo "::warning::$latest is not on dev history; this release repairs the legacy divergence."
    else
      echo "::error::Latest release tag $latest is absent from both promotion histories."
      exit 1
    fi
  fi
fi

if [[ -n "$base_range" ]]; then
  count=$(git rev-list --count "$base_range")
  echo "Commits in promoted dev since $latest: $count"
  if [[ "$count" -eq 0 && "$FORCE" != "true" ]]; then
    echo "No new promoted commits since $latest; skipping release."
    write_output tagged false
    exit 0
  fi
fi

version="${latest#v}"
if [[ ! "$version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  echo "::error::Latest release tag $latest is not a vMAJOR.MINOR.PATCH version."
  exit 1
fi

major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
patch="${BASH_REMATCH[3]}"

case "$BUMP" in
  major)
    major=$((major + 1))
    minor=0
    patch=0
    ;;
  minor)
    minor=$((minor + 1))
    patch=0
    ;;
  patch)
    patch=$((patch + 1))
    ;;
  *)
    echo "::error::Unknown version bump '$BUMP'."
    exit 1
    ;;
esac

next="v${major}.${minor}.${patch}"
if git rev-parse --quiet --verify "refs/tags/$next" >/dev/null; then
  echo "::error::Tag $next already exists."
  exit 1
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git tag --annotate "$next" "$source_sha" --message "Release $next"
git push origin "refs/tags/$next"

echo "Tagged promoted dev commit $source_sha as $next."
write_output tagged true
write_output version "$next"
write_output source_sha "$source_sha"
