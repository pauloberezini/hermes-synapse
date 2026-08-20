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
    # Simple scrub if OSS_README doesn't exist
    sed -i '' -E 's/trading|hedge fund|crypto|bcm|alpaca|ccxt/AI assistant/gi' "$DEST/README.md"
fi

if [ -f "$DEST/.env.example" ]; then
    sed -i '' -e '/BCM_/d' -e '/ALPACA_/d' -e '/CCXT_/d' -e '/BYBIT_/d' "$DEST/.env.example"
fi

echo "Export completed successfully to $DEST."
echo "You can now cd to $DEST, init a new git repo, and push to your open source GitHub."
