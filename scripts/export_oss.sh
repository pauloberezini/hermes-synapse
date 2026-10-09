#!/usr/bin/env bash
# Publish the OSS core to the public repo. Private plugin tree is excluded as a whole.
# Keep exclusions in sync with .cursor/rules/oss-private-boundary.mdc
#
#   scripts/export_oss.sh            # sync into a fresh clone at $DEST, show diff, no push
#   scripts/export_oss.sh --push     # also commit + push to $PUBLIC_REMOTE $PUBLIC_BRANCH
#   TAG=v1.4.0 scripts/export_oss.sh --push   # and push a release tag (release.yml creates the GitHub release)
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-/tmp/hermes-synapse-oss}"
PUBLIC_REMOTE="${PUBLIC_REMOTE:-https://github.com/pauloberezini/hermes-synapse.git}"
PUBLIC_BRANCH="${PUBLIC_BRANCH:-main}"

if [ ! -d "$DEST/.git" ]; then
    rm -rf "$DEST"
    git clone --quiet --branch "$PUBLIC_BRANCH" "$PUBLIC_REMOTE" "$DEST"
fi

# Only files git would track (respects .gitignore: no .env, DBs, venvs, node_modules),
# minus the private tree.
PRIVATE_PATHS='^(backend/bcm/|\.github/workflows/private-ci\.yml$|backend/openapi/|scripts/ctrader_lookup\.py$|docs/specs/bcm-|docs/specs/plugin-boundary-plan\.md$|\.cursor/|[^/]*_TRADE_AUDIT_[^/]*\.md$)'
FILES="$(mktemp)"
git -C "$SRC" ls-files -co --exclude-standard | grep -vE "$PRIVATE_PATHS" > "$FILES"

find "$DEST" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
rsync -a --files-from="$FILES" "$SRC/" "$DEST/"
rm -f "$FILES"

# Belt and braces: templates must not carry private keys even if someone edits them here.
sed -i.bak -E '/^(BCM_|CTRADER_|ALPACA_|CCXT_|FRED_)/d' "$DEST/.env.example" && rm -f "$DEST/.env.example.bak"
if [ -f "$DEST/docker-compose.yml" ]; then
    sed -i.bak -E '/(BCM_|CTRADER_)/d' "$DEST/docker-compose.yml" && rm -f "$DEST/docker-compose.yml.bak"
fi

# Leak gate: private imports / env keys / broker names abort the publish.
leaks=$(grep -rIl -E 'backend\.bcm|from bcm|BCM_[A-Z]|CTRADER_[A-Z]|[Pp]epperstone' "$DEST" --exclude-dir=.git --exclude-dir=node_modules --exclude=export_oss.sh || true)
if [ -n "$leaks" ]; then
    echo "LEAK: private references found in export:" >&2
    echo "$leaks" >&2
    exit 1
fi
# Coupling smell (tool names hardcoded in core) is reported, not blocking. Track it down to zero.
smell=$({ grep -rIoiE '\b(bcm_|ctrader_)[a-z_]+' "$DEST/backend" --include='*.py' --exclude-dir=tests || true; } | wc -l | tr -d ' ')
echo "Coupling smell: $smell hardcoded plugin tool-name references in backend/*.py (target: 0)."

cd "$DEST"
git add -A
if git diff --cached --quiet; then
    echo "OSS export: nothing to publish (in sync with $PUBLIC_BRANCH)."
else
    git --no-pager diff --cached --stat | tail -n 20
fi

if [ "${1:-}" = "--push" ]; then
    if ! git diff --cached --quiet; then
        git commit --quiet -m "${MSG:-release: sync OSS core from private tree}"
    fi
    git push "$PUBLIC_REMOTE" "HEAD:$PUBLIC_BRANCH"
    if [ -n "${TAG:-}" ]; then
        git tag -a "$TAG" -m "$TAG"
        git push "$PUBLIC_REMOTE" "$TAG"
    fi
    echo "Published to $PUBLIC_REMOTE $PUBLIC_BRANCH${TAG:+ and tagged $TAG}."
else
    echo "Dry run. Re-run with --push to publish. Export tree: $DEST"
fi
