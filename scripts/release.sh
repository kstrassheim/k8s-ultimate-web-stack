#!/usr/bin/env bash
# Cut a release tag that ArgoCD rolls out (test immediately, prod after approval).
#
#   scripts/release.sh 0.9.0
#
# Pins the test/prod overlay images to immutable per-tag tags and creates the
# git tag whose tree carries those pins:
#   k8s/environments/test/kustomization.yaml  -> newTag v0.9.0-test
#   k8s/environments/prod/kustomization.yaml  -> newTag v0.9.0-prod
#
# The release commit is reachable only via the tag — main is left untouched
# (the tag is the source of truth for the test/prod ArgoCD apps, which track
# targetRevision "*"). Pushing the tag triggers build-images.yml: web:<tag>-test
# builds and rolls test at once; web:<tag>-prod builds + rolls prod only once the
# `prod` GitHub environment is approved.
set -euo pipefail

ver="${1:-}"
[ -n "$ver" ] || { echo "usage: $0 <semver, e.g. 0.9.0>" >&2; exit 1; }
[[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be X.Y.Z (got '$ver')" >&2; exit 1; }
tag="v${ver}"

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

[ -z "$(git status --porcelain)" ] || { echo "working tree not clean; commit/stash first" >&2; exit 1; }
git rev-parse -q --verify "refs/tags/${tag}" >/dev/null 2>&1 && { echo "tag ${tag} already exists" >&2; exit 1; }

base="$(git rev-parse HEAD)"
test_ks="k8s/environments/test/kustomization.yaml"
prod_ks="k8s/environments/prod/kustomization.yaml"

# Pin immutable per-env image tags (only the indented `newTag:` line).
sed -i -E "s#^([[:space:]]*newTag:).*#\1 ${tag}-test#" "$test_ks"
sed -i -E "s#^([[:space:]]*newTag:).*#\1 ${tag}-prod#" "$prod_ks"
grep -q "newTag: ${tag}-test" "$test_ks" || { echo "failed to pin test newTag" >&2; git checkout -- "$test_ks" "$prod_ks"; exit 1; }
grep -q "newTag: ${tag}-prod" "$prod_ks" || { echo "failed to pin prod newTag" >&2; git checkout -- "$test_ks" "$prod_ks"; exit 1; }

git add "$test_ks" "$prod_ks"
git commit -q -m "release: ${tag}"
git tag -a "${tag}" -m "release ${tag}"
git push origin "refs/tags/${tag}"

# Leave the branch as it was — the release lives under the tag, not on main.
git reset -q --hard "${base}"
echo "pushed tag ${tag} (main unchanged). CI now builds test now / prod after approval."
