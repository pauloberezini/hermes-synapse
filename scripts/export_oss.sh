#!/usr/bin/env bash
set -e

echo "Starting OSS Export..."

# Destination directory
DEST="/tmp/hermes-synapse-oss"
rm -rf "$DEST"
mkdir -p "$DEST"

# Copy the entire working directory (excluding .git and the destination itself if nested)
rsync -a --exclude='.git' --exclude='backend/bcm' --exclude='backend/openapi' --exclude='scripts/ctrader_lookup.py' --exclude='__pycache__' ./ "$DEST/"

echo "Sanitizing documentation..."
if [ -f "$DEST/docs/OSS_README.md" ]; then
    cp "$DEST/docs/OSS_README.md" "$DEST/README.md"
else
    # Simple scrub if OSS_README doesn't exist (portable across BSD/macOS and GNU sed)
    sed -i.bak -E 's/trading|hedge fund|crypto|bcm|alpaca|ccxt/AI assistant/gi' "$DEST/README.md"
    rm -f "$DEST/README.md.bak"
fi

if [ -f "$DEST/.env.example" ]; then
    sed -i.bak -e '/BCM_/d' -e '/ALPACA_/d' -e '/CCXT_/d' -e '/BYBIT_/d' "$DEST/.env.example"
    rm -f "$DEST/.env.example.bak"
fi

echo "Export completed successfully to $DEST."
echo "You can now cd to $DEST, init a new git repo, and push to your open source GitHub."
